from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
from werkzeug.utils import secure_filename
import os
import json
import time
from datetime import datetime
import logging
import traceback

# Import your existing scripts as modules
import anyror_new
import anyrortoTSR

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('output', exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Setup logging
def setup_app_logging():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/webapp_{timestamp}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_app_logging()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch-anyror', methods=['POST'])
def fetch_anyror():
    logger.info("Starting AnyRoR data fetch")
    try:
        # Get form data
        district = request.form.get('district')
        taluka = request.form.get('taluka')
        village = request.form.get('village')
        survey_block = request.form.get('survey_block')
        
        logger.info(f"Fetching data for District: {district}, Taluka: {taluka}, Village: {village}, Survey: {survey_block}")
        
        # Store parameters in session
        session['anyror_params'] = {
            'district': district,
            'taluka': taluka,
            'village': village,
            'survey_block': survey_block
        }
        
        # Generate a unique filename for this request
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f"land_record_{timestamp}.pdf"
        pdf_path = os.path.join('uploads', pdf_filename)
        
        # Call the modified anyror_new function
        result = anyror_new.fetch_land_record(
            district_name=district,
            taluka_name=taluka,
            village_name=village,
            survey_block_number=survey_block,
            output_path=pdf_path,
            logger=logger
        )
        
        if result['success']:
            session['pdf_path'] = pdf_path
            return jsonify({
                'success': True,
                'message': 'Land record PDF generated successfully',
                'pdf_path': pdf_path
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Error: {result['error']}"
            })
            
    except Exception as e:
        logger.error(f"Error in fetch-anyror: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f"An unexpected error occurred: {str(e)}"
        })

@app.route('/generate-tsr', methods=['POST'])
def generate_tsr():
    logger.info("Starting TSR generation")
    try:
        # First check if a file is being uploaded in this request
        if 'pdf_file' in request.files and request.files['pdf_file'].filename:
            pdf_file = request.files['pdf_file']
            filename = secure_filename(pdf_file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(pdf_path)
            session['pdf_path'] = pdf_path
            logger.info(f"Using uploaded PDF file: {pdf_path}")
        else:
            # If no file uploaded, check session for previously fetched/uploaded PDF
            pdf_path = session.get('pdf_path')
            if not pdf_path or not os.path.exists(pdf_path):
                return jsonify({
                    'success': False,
                    'message': 'No PDF file available. Please fetch AnyRoR data or upload a PDF.'
                })
            logger.info(f"Using existing PDF from session: {pdf_path}")
        
        # Generate output filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tsr_filename = f"TSR_output_{timestamp}.docx"
        tsr_path = os.path.join('output', tsr_filename)
        
        # Call the modified anyrortoTSR function
        result = anyrortoTSR.generate_tsr_from_pdf(
            pdf_path=pdf_path,
            output_path=tsr_path,
            logger=logger
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'TSR document generated successfully',
                'tsr_path': tsr_path
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Error: {result['error']}"
            })
            
    except Exception as e:
        logger.error(f"Error in generate-tsr: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f"An unexpected error occurred: {str(e)}"
        })

@app.route('/download/<path:filename>')
def download_file(filename):
    directory = os.path.dirname(filename)
    file = os.path.basename(filename)
    return send_file(os.path.join(directory, file), as_attachment=True)

@app.route('/debug-extraction', methods=['POST'])
def debug_extraction():
    logger.info("Starting debug extraction")
    try:
        if 'pdf_file' in request.files and request.files['pdf_file'].filename:
            pdf_file = request.files['pdf_file']
            filename = secure_filename(pdf_file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(pdf_path)
            
            # Extract text from PDF
            pdf_text = anyrortoTSR.extract_text_from_pdf(pdf_path)
            if pdf_text is None:
                return jsonify({
                    'success': False,
                    'message': 'Failed to extract text from PDF'
                })
            
            # Extract land details
            land_details = anyrortoTSR.extract_land_details(pdf_text)
            
            # Extract entries
            entries = anyrortoTSR.extract_entry_details(pdf_text)
            
            return jsonify({
                'success': True,
                'land_details': land_details,
                'entries_count': len(entries),
                'sample_entries': entries[:3] if entries else []
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No PDF file uploaded'
            })
    except Exception as e:
        logger.error(f"Error in debug-extraction: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f"An error occurred: {str(e)}"
        })

if __name__ == '__main__':
    app.run(debug=True) 