import os
import mysql.connector # Import MySQL connector
from mysql.connector import Error # Import Error class
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename # For secure file handling

# --- Configuration ---
# !! IMPORTANT: Use environment variables or a config file for production !!
# Replace with your actual MySQL connection details.
MYSQL_HOST = 'localhost'        # Or your MySQL server IP/hostname
MYSQL_USER = 'csr_user'         # The user you created in MySQL
MYSQL_PASSWORD = 'prince' # The password you set for 'csr_user'
MYSQL_DB = 'csr_db'             # The database you created in MySQL

UPLOAD_FOLDER = 'uploads' # Make sure this folder exists
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024 # 5 MB limit

# --- Flask App Setup ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
# !! CHANGE THIS SECRET KEY FOR PRODUCTION !!
app.config['SECRET_KEY'] = 'a_very_insecure_default_key_replace_me'

# --- Database Functions ---
def get_db():
    """Connects to the MySQL database."""
    conn = None
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        print("MySQL Connection successful")
    except Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        # Returning None indicates connection failure
    return conn

# --- Helper Functions ---
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    """Renders the main page with the CSR form."""
    return render_template('index.html')

@app.route('/submit_csr', methods=['POST'])
def submit_csr():
    """Handles the CSR form submission."""
    # --- Get Form Data ---
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    phone = request.form.get('phone', '') # Optional, default to empty string
    customer_id = request.form.get('customer_id', '') # Optional
    request_type = request.form.get('request_type')
    subject = request.form.get('subject')
    description = request.form.get('description')
    city = request.form.get('city', '') # Optional
    state = request.form.get('state', '') # Optional
    postal_code = request.form.get('postal_code', '') # Optional
    contact_time = request.form.get('contact_time', 'Any Time')
    confirmation = request.form.get('confirmation') # Checkbox value is 'on' if checked

    # --- Basic Validation ---
    if not all([full_name, email, request_type, subject, description, confirmation]):
         flash('Error: Please fill in all required fields (*) and confirm accuracy.', 'error')
         # In a real app, you might repopulate the form with previous values here
         return redirect(url_for('index') + '#csr-form') # Redirect back to form section

    # --- Handle File Upload ---
    file_path_on_disk = None # Full path for saving/deleting
    uploaded_filename_for_db = None # Just the filename to store in DB

    if 'attachment' in request.files:
        file = request.files['attachment']
        # Check if user selected a file
        if file and file.filename != '':
            if allowed_file(file.filename):
                try:
                    # Secure the filename
                    filename = secure_filename(file.filename)
                    # In a real app, consider adding a unique prefix (timestamp/UUID)
                    # filename = str(uuid.uuid4()) + "_" + filename
                    file_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path_on_disk)
                    uploaded_filename_for_db = filename # Store just the filename in DB
                    print(f"File saved successfully: {file_path_on_disk}")
                except Exception as e:
                    print(f"Error saving file: {e}")
                    # Decide if file upload error is critical or not
                    flash('Warning: Could not upload the file. Submitting request without it.', 'error')
                    # Or: flash('Error uploading file. Please try again.', 'error'); return redirect(...)
            else:
                flash('Error: Invalid file type. Allowed: {}'.format(', '.join(ALLOWED_EXTENSIONS)), 'error')
                return redirect(url_for('index') + '#csr-form')


    # --- Store in MySQL Database ---
    conn = None # Initialize connection variable
    cursor = None # Initialize cursor variable
    try:
        conn = get_db()
        # Check if connection was successful
        if conn is None or not conn.is_connected():
             flash('Error: Database connection failed. Please try again later.', 'error')
             # Clean up uploaded file if DB connection failed before insert attempt
             if file_path_on_disk and os.path.exists(file_path_on_disk):
                 try: os.remove(file_path_on_disk)
                 except OSError: pass # Ignore error if file removal fails
             return redirect(url_for('index') + '#csr-form')

        cursor = conn.cursor()

        # Use %s placeholders for MySQL query parameters
        sql = '''
            INSERT INTO requests
                (full_name, email, phone, customer_id, request_type, subject, description, file_path, city, state, postal_code, preferred_contact_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        # Pass values as a tuple in the correct order
        values = (
            full_name, email, phone, customer_id, request_type,
            subject, description, uploaded_filename_for_db, city, state,
            postal_code, contact_time
        )

        cursor.execute(sql, values)
        conn.commit() # Commit the transaction to save changes

        flash('Success! Your request has been submitted. We will get back to you soon.', 'success')
        print(f"Form data inserted into MySQL for {email}")

    except Error as e:
        print(f"MySQL Database error during insert: {e}")
        flash('Error: An internal error occurred while submitting your request. Please try again later.', 'error')
        # Attempt to clean up the saved file if the DB insert failed
        if file_path_on_disk and os.path.exists(file_path_on_disk):
             try:
                 os.remove(file_path_on_disk)
                 print(f"Cleaned up file due to DB error: {file_path_on_disk}")
             except OSError as rm_err:
                 print(f"Error removing file during cleanup: {rm_err}")

    finally:
        # Ensure cursor and connection are closed properly
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection is closed.")

    return redirect(url_for('index') + '#csr-form') # Redirect back to form section


# --- Database Initialization Command (Run once: flask --app app init-db) ---
@app.cli.command('init-db')
def init_db_command():
    """Drops existing table (if any) and creates a new requests table in MySQL."""
    conn = None
    cursor = None
    try:
        # Connect to MySQL
        conn = get_db()
        if conn is None or not conn.is_connected():
            print("Error: Failed to connect to database for initialization.")
            return

        cursor = conn.cursor()

        print("Dropping existing 'requests' table (if it exists)...")
        # Use backticks for table name if needed, though 'requests' is usually fine
        cursor.execute('DROP TABLE IF EXISTS `requests`')

        print("Creating new 'requests' table...")
        # Adjusted CREATE TABLE syntax for MySQL data types
        cursor.execute('''
            CREATE TABLE `requests` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `submission_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                `full_name` VARCHAR(255) NOT NULL,
                `email` VARCHAR(255) NOT NULL,
                `phone` VARCHAR(50) NULL,
                `customer_id` VARCHAR(100) NULL,
                `request_type` VARCHAR(100) NOT NULL,
                `subject` VARCHAR(255) NOT NULL,
                `description` TEXT NOT NULL,
                `file_path` VARCHAR(512) NULL,
                `city` VARCHAR(100) NULL,
                `state` VARCHAR(100) NULL,
                `postal_code` VARCHAR(20) NULL,
                `preferred_contact_time` VARCHAR(50) NULL,
                INDEX `idx_email` (`email`), -- Add index on email for potential lookups
                INDEX `idx_request_type` (`request_type`) -- Add index on type
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        ''')
        conn.commit()
        print('Success: Initialized the MySQL database and created the requests table.')

    except Error as e:
        print(f"Error during database initialization: {e}")
    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Initialization connection closed.")


# --- Run the Flask App ---
if __name__ == '__main__':
    # Create the uploads directory if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        try:
            os.makedirs(UPLOAD_FOLDER)
            print(f"Created upload directory: {UPLOAD_FOLDER}")
        except OSError as e:
            print(f"Error creating upload directory {UPLOAD_FOLDER}: {e}")
            # Decide if this is critical enough to stop the app

    # Run the Flask development server
    # Set debug=False for production environments
    app.run(debug=True, host='0.0.0.0', port=5000)