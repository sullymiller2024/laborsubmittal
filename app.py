from flask import Flask, request, redirect, url_for, render_template, send_file
import fitz  
import io
import pandas as pd
import openai
import os
import re
import pdfplumber
from openai import OpenAI

app = Flask(__name__)

# Global variable for Tier 2 zip codes
tier_2_zip_codes = [
    '90001', '90002', '90003', '90005', '90006', '90007', '90008', '90010', '90011', '90012',
    '90013', '90014', '90015', '90016', '90017', '90018', '90019', '90020', '90021', '90022',
    '90023', '90026', '90028', '90029', '90031', '90032', '90033', '90034', '90035', '90036',
    '90037', '90038', '90040', '90042', '90043', '90044', '90047', '90057', '90058', '90059',
    '90061', '90062', '90063', '90065', '90089', '90201', '90220', '90221', '90222', '90242',
    '90247', '90250', '90255', '90260', '90262', '90270', '90280', '90301', '90302', '90303',
    '90304', '90501', '90601', '90602', '90640', '90706', '90710', '90716', '90723', '90731',
    '90744', '90802', '90804', '90805', '90806', '90810', '90813', '91001', '91042', '91046',
    '91103', '91201', '91203', '91204', '91205', '91303', '91331', '91335', '91340', '91343',
    '91352', '91401', '91402', '91405', '91406', '91411', '91502', '91601', '91605', '91606',
    '91702', '91706', '91731', '91732', '91733', '91744', '91746', '91755', '91766', '91767',
    '91768', '91770'
]

def extract_text_from_pdf(pdf_path, chunk_size=10):
    with fitz.open(pdf_path) as doc:
        for start in range(0, doc.page_count, chunk_size):
            text = ''
            for page_num in range(start, min(start + chunk_size, doc.page_count)):
                page = doc.load_page(page_num)
                text += page.get_text("text")
            yield text

def analyze_text_chunk(text_chunk, chunk_index, client, summary_df):
    prompt_text = """
    Given the text extracted from a construction project PDF, identify and summarize the labor information based on the categories mentioned:
    - Targeted Labor: Specify the percentage and conditions for targeted labor.
    - Local Labor: Percentage required and specific conditions and list all zip codes i need all of them every single zip codes donot summerize them , donot say from a zip code to a zip code print out ALL zip code EVERY SINGLE ZIP CODE  that mentioned donot miss any of the zip codes it is ok if they are many give a list of all of them without summerize  .
    - Minority Labor: Percentage and conditions.
    - Women/Female Labor: Percentage and conditions.
      there are some hiring or requirnment like DBE or CBE or any BEs contractors they donot count as minority labors.
      Analyze the text and provide detailed summaries for each category mentioned above, highlighting any specific conditions or requirements noted in the text.Donot forget for listing zipcodes of any tiers for local labors if there is any.
      Analyze the text and provide detailed summaries for each category, highlighting specific conditions.Be very careful because i donot want to miss any information.
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "Extract labor data from the following text"},
            {"role": "user", "content": prompt_text + text_chunk}
        ]
    )
    result = response.choices[0].message.content

    # Append result to summary_df DataFrame
    categories = ["Targeted Labor", "Local Labor", "Minority Labor", "Women/Female Labor"]
    for category in categories:
        match = re.search(f'{category}: (.*?)\n', result)
        if match:
            percentage_conditions = match.group(1)
            summary_df = summary_df.append({'Category': category, 'Percentage and Conditions': percentage_conditions}, ignore_index=True)

    # Save the result to a text file
    with open(f"analysis_result_chunk_{chunk_index}.txt", "w") as file:
        file.write(result)
    return summary_df

def compile_summaries(output_directory):
    summaries = []
    for filename in os.listdir(output_directory):
        if filename.startswith("analysis_result_chunk_") and filename.endswith(".txt"):
            with open(os.path.join(output_directory, filename), "r") as file:
                content = file.read()
            summaries.append(content)
    summary_text = "\n\n".join(summaries)
    with open("final_summary.txt", "w") as file:
        file.write(summary_text)
    print("Compiled summary saved to final_summary.txt")

def extract_zip_codes_from_text(text):
    zip_code_pattern = r'\b\d{5}\b'
    zip_codes = re.findall(zip_code_pattern, text)
    return set(zip_codes)

def compile_labor_data_to_excel(data, filename="labor_data.xlsx"):
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data compiled to Excel file: {filename}")

def compare_with_available_labor(required_zip_codes, available_labor_path):
    available_labor_df = pd.read_excel(available_labor_path)
    # Filter available labor by required zip codes
    matched_labor = available_labor_df[available_labor_df['ZIP/Postal Code'].isin(required_zip_codes)]
    matched_labor['Tier 2'] = matched_labor['ZIP/Postal Code'].apply(lambda x: "Yes" if x in tier_2_zip_codes else "No")
    job_title_counts = matched_labor['Free Form Job Title'].value_counts().reset_index()
    job_title_counts.columns = ['Job Title', 'Count']
    job_title_counts.to_excel("matched_labor_data.xlsx", index=False)
    return job_title_counts

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        if 'pdf_file' not in request.files or 'excel_file' not in request.files:
            return 'No file part'

        pdf_file = request.files['pdf_file']
        excel_file = request.files['excel_file']

        if pdf_file.filename == '' or excel_file.filename == '':
            return 'No selected file'

        # Ensure the 'uploads' directory exists
        if not os.path.exists('uploads'):
            os.makedirs('uploads')

        pdf_path = os.path.join('uploads', pdf_file.filename)
        excel_path = os.path.join('uploads', excel_file.filename)

        pdf_file.save(pdf_path)
        excel_file.save(excel_path)

        # Process the files synchronously
        process_files(pdf_path, excel_path)

        return 'Files processed successfully. Check the result files.'

    return render_template('upload_form.html')

def process_files(pdf_path, excel_path):
    api_key = os.environ.get('OPENAI_API_KEY')
    all_zip_codes = set()
    client = openai.Client(api_key=api_key)
    output_directory = "."
    summary_df = pd.DataFrame(columns=['Category', 'Percentage and Conditions'])

    for i, text_chunk in enumerate(extract_text_from_pdf(pdf_path)):
        summary_df = analyze_text_chunk(text_chunk, i, client, summary_df)
        print(f"Processed chunk {i+1}")

    summary_df.to_excel("labor_summary.xlsx", index=False)

    compile_summaries(output_directory)

    for filename in os.listdir(output_directory):
        if filename.startswith("final_summary") and filename.endswith(".txt"):
            with open(os.path.join(output_directory, filename), "r") as file:
                content = file.read()
                zip_codes = extract_zip_codes_from_text(content)
                all_zip_codes.update(zip_codes)

    # Comparing with available labor
    matched_labor = compare_with_available_labor(all_zip_codes, excel_path)
    compile_labor_data_to_excel(matched_labor, "matched_labor_data.xlsx")

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
