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
    '90001', '90002', '90003', '90004', '90005', '90006', '90007', '90008', '90010', '90011', '90012',
     '90014', '90015', '90016', '90017', '90018', '90019', '90020', '90021', '90022',
    '90023', '90026', '90028', '90029', '90031', '90032', '90033', '90034', '90035', '90036',
    '90037', '90038', '90040', '90042', '90043', '90044', '90047', '90057', '90058', '90059',
    '90061', '90062', '90063', '90089', '90201', '90220', '90221', '90222', '90242',
    '90247', '90250', '90255', '90262', '90270', '90280', '90301', '90302', '90303',
    '90304', '90401', '90501', '90601', '90602', '90640', '90706', '90716', '90723', '90731',
    '90744', '90802', '90804', '90805', '90806', '90810', '90813', '91001', '91046',
    '91103', '91201', '91203', '91204', '91205', '91303', '91331', '91335', '91340','91342', '91343',
    '91352', '91401', '91402', '91405', '91406', '91411', '91502', '91601', '91605', '91606',
    '91702', '91706', '91731', '91732', '91733', '91744', '91746', '91754','91755', '91766', '91767',
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
    if it mentioned "tire 2"  as requered zip codes that means thye need labor from this list [ '90001', '90002', '90003', '90004', '90005', '90006', '90007', '90008', '90010', '90011', '90012',
     '90014', '90015', '90016', '90017', '90018', '90019', '90020', '90021', '90022',
    '90023', '90026', '90028', '90029', '90031', '90032', '90033', '90034', '90035', '90036',
    '90037', '90038', '90040', '90042', '90043', '90044', '90047', '90057', '90058', '90059',
    '90061', '90062', '90063', '90089', '90201', '90220', '90221', '90222', '90242',
    '90247', '90250', '90255', '90262', '90270', '90280', '90301', '90302', '90303',
    '90304', '90401', '90501', '90601', '90602', '90640', '90706', '90716', '90723', '90731',
    '90744', '90802', '90804', '90805', '90806', '90810', '90813', '91001', '91046',
    '91103', '91201', '91203', '91204', '91205', '91303', '91331', '91335', '91340','91342', '91343',
    '91352', '91401', '91402', '91405', '91406', '91411', '91502', '91601', '91605', '91606',
    '91702', '91706', '91731', '91732', '91733', '91744', '91746', '91754','91755', '91766', '91767',
    '91768', '91770'] so return th whole zip codes if you find tier 2 word in the text if there is not tier 2 in the text donot return this list , be careful tier must be with 2 "tier 2",  from these list beside other zip codes they mentioned. I need all zip codes every single one. do not miss even 1 zip code
    - Minority Labor: Percentage and conditions.
    - Women/Female Labor: Percentage and conditions.
      there are some hiring or requirnment like DBE or CBE or any BEs contractors they donot count as minority labors.
      Analyze the text and provide detailed summaries for each category mentioned above, highlighting any specific conditions or requirements noted in the text.Donot forget for listing zipcodes of any tiers for local labors if there is any.
      Analyze the text and provide detailed summaries for each category, highlighting specific conditions.Be very careful because i donot want to miss any infprmation.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
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
    with open(os.path.join(output_directory,"final_summary.txt"), "w") as file:
        file.write(summary_text)
    

def extract_zip_codes_from_text(text):
    zip_code_pattern = r'\b(\d{5})-?\d*\b'
    zip_codes = re.findall(zip_code_pattern, text)
    return set(zip_codes)

def compile_labor_data_to_excel(data, filename="labor_data.xlsx"):
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
   

def compare_with_available_labor(required_zip_codes, available_labor_path):
    available_labor_df = pd.read_excel(available_labor_path)
    # Filter available labor by required zip codes
    matched_labor = available_labor_df[available_labor_df['ZIP/Postal Code'].isin(required_zip_codes)]
    sorted_and_counted= matched_labor['Free Form Job Title'].value_counts().reset_index()
    sorted_and_counted.columns = ['Job Title', 'Count']
    return sorted_and_counted

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
# Generate download links
        summary_link = url_for('download_file', filename='labor_summary.xlsx')
        matched_labor_link = url_for('download_file', filename='matched_labor_data.xlsx')
        final_summary_link = url_for('download_file', filename='final_summary.txt')

        return f'''
        Files processed successfully. <br>
        <a href="{summary_link}">Download Labor Summary Excel</a><br>
        <a href="{matched_labor_link}">Download Matched Labor Data Excel</a><br>
        <a href="{final_summary_link}">Download Final Summary Text</a>
        '''

    return render_template('upload_form.html')


def process_files(pdf_path, excel_path):
    api_key = os.environ.get('OPENAI_API_KEY')
    all_zip_codes = set()
    client = openai.Client(api_key=api_key)
    output_directory = os.path.join(app.root_path,'uploads')
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    summary_df = pd.DataFrame(columns=['Category', 'Percentage and Conditions'])

    for i, text_chunk in enumerate(extract_text_from_pdf(pdf_path)):
        summary_df = analyze_text_chunk(text_chunk, i, client, summary_df)
        print(f"Processed chunk {i+1}")

    summary_df.to_excel(os.path.join(output_directory,"labor_summary.xlsx"), index=False)

    compile_summaries(output_directory)

    for filename in os.listdir(output_directory):
        if filename.startswith("final_summary") and filename.endswith(".txt"):
            with open(os.path.join(output_directory, filename), "r") as file:
                content = file.read()
                zip_codes = extract_zip_codes_from_text(content)
                all_zip_codes.update(zip_codes)

    # Comparing with available labor
    matched_labor = compare_with_available_labor(all_zip_codes, excel_path)
    compile_labor_data_to_excel(matched_labor, os.path.join(output_directory,"matched_labor_data.xlsx"))

@app.route('/download/<filename>')
def download_file(filename):
    filepath=os.path.join('uploads',filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return "File not found",404

@app.route('/process_chunk',methods=['POST'])
def process_chunk():
    pdf_path = request.form.get('pdf_path')
    chunk_index=int(request.form.get('chunk_index',0))
    all_zip_codes = set()
    client = openai.Client(api_key=os.environ.get('OPENAI_API_KEY'))
    output_directory = os.path.join(app.root_path, 'uploads')
    summary_df = pd.DataFrame(columns=['Category','Percentage and Conditions'])
    for i, text_chunk in enumerate(extract_text_from_pdf(pdf_path)):
        if i == chunk_index:
            summary_df = analyze_text_chunk(text_chunnk, i, client, summary_df)
            break
    summary_df.to_excel(os.path.join(output_directory, f"labor_summary_{chunk_index}.xlsx"),index=False)
    return jsonify({'status': 'processed','next_chunk':chunk_index +1})
        
   

if __name__ == "__main__":
    app.run(debug=True)
