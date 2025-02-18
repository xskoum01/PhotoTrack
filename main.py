from datetime import datetime
from flask import Flask, request, flash, redirect, url_for, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError
import os
import urllib.parse
import pyodbc
from flask_cors import CORS

# Flask aplikace
app = Flask(__name__)
CORS(app, resources={r"/upload": {"origins": "*"}})

# Připojení k Azure Blob Storage
# Pro lokální testování
#blob_connect_str = "DefaultEndpointsProtocol=https;AccountName=vsmphototrackstorage;AccountKey=KNjm7pyqb7yAqBX8ztxmMrxoD0TafLaQj+BLX+tS4AvNFZkd4+FVOU4PbpXYIv2gQvoSsM6q2LUt+AStfj+N7w==;EndpointSuffix=core.windows.net"

blob_connect_str = os.environ.get("AZURE_BLOB_CONNECTION_STRING")

blob_service_client = BlobServiceClient.from_connection_string(blob_connect_str)
container_name = "photos"

# Vytvoření kontejneru, pokud neexistuje
container_client = blob_service_client.get_container_client(container_name)
try:
    container_client.create_container()
except ResourceExistsError:
    pass

# Konfigurace pro SQLite databázi (pro přihlašování)
basedir = os.path.abspath(os.path.dirname(__file__))
#app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "users.db")}'
#app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#app.config['SECRET_KEY'] = 'your_secret_key'

# SQL databaze
# Získání připojovacího řetězce z proměnných prostředí
connection_string = os.environ.get("AZURE_SQL_CONNECTION_STRING")

# Zakódování parametrů do správného formátu pro SQLAlchemy
encoded_connection_string = urllib.parse.quote_plus(connection_string)

# Použití správného formátu URI pro SQLAlchemy s PyODBC
app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc:///?odbc_connect={encoded_connection_string}"


# Inicializace databáze a Flask-Login
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modely databáze (pouze pro přihlašování)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

# Model konfigurace fotopasti
class Configuration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wakeUp_time = db.Column(db.String(50), nullable=False)
    interval_shots = db.Column(db.String(50), nullable=False)
    photo_resolution = db.Column(db.String(50), nullable=False)
    photo_quality = db.Column(db.String(50), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)

# Funkce pro načtení uživatele
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# API endpoint pro načtení konfigurace
@app.route('/get_configuration', methods=['GET'])
@login_required
def get_configuration():
    config = Configuration.query.filter_by(user_id=current_user.id).first()

    if not config:
        return jsonify({"message": "No configuration found"}), 404

    return jsonify({
        "wakeUp_time": config.wakeUp_time,
        "interval_shots": config.interval_shots,
        "photo_resolution": config.photo_resolution,
        "photo_quality": config.photo_quality,
        "phone_number": config.phone_number,
    })


@app.route('/save_configuration', methods=['POST'])
@login_required
def save_configuration():
    try:
        data = request.json
        print(f"Received JSON: {data}")  # Debugging

        config = Configuration.query.filter_by(user_id=current_user.id).first()

        if config is None:
            config = Configuration(user_id=current_user.id)
            db.session.add(config)

        config.wakeUp_time = data.get('wakeUp_time', '60 s')
        config.interval_shots = data.get('interval_shots', '5 s')
        config.photo_resolution = data.get('photo_resolution', '1024x768')
        config.photo_quality = data.get('photo_quality', 'High')
        config.phone_number = data.get('phone_number', '+420735009345')

        db.session.commit()
        return jsonify({"message": "Configuration saved successfully"}), 200

    except Exception as e:
        print(f"Error: {str(e)}")  # Logování chyby do konzole
        return jsonify({"error": "Error saving configuration", "details": str(e)}), 500



# Přihlašovací stránka
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and user.password_hash == password:
            login_user(user)
            flash('Successfully logged in', 'Success')
            return redirect(url_for('PhotoTrackCalendar'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

# Upload obrázku a metadat
@app.route('/upload', methods=['POST'])
def upload_photo():
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    # Přidání časové značky k názvu souboru a přípony .jpg
    jpgExtension = ".jpg"
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    new_filename = f"{timestamp}_{file.filename}{jpgExtension}"

    # Metadata z požadavku
    battery_level = request.form.get('battery_level', 'Unknown')
    charging_status = request.form.get('charging_status', 'Unknown')
    time_to_dead = request.form.get('time_to_dead', 'Unknown')
    date_taken = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    # Nahrání souboru do Azure Blob Storage
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=new_filename)
    blob_client.upload_blob(file.read(), overwrite=False, metadata={
        "date_taken": date_taken,
        "battery_level": battery_level,
        "charging_status": charging_status,
        "time_to_dead": time_to_dead
    })

    return "File and metadata uploaded successfully", 200

# Načítání fotografií a metadat
@app.route('/get_events', methods=['GET'])
@login_required
def get_events():
    events = []
    blobs = container_client.list_blobs()

    for blob in blobs:
        blob_client = container_client.get_blob_client(blob)
        blob_properties = blob_client.get_blob_properties()

        events.append({
            "title": blob.name,
            "start": blob_properties.metadata.get("date_taken", ""),
            "image": blob_client.url,
            "battery_level": blob_properties.metadata.get("battery_level", "Unknown"),
            "charging_status": blob_properties.metadata.get("charging_status", "Unknown"),
            "time_to_dead": blob_properties.metadata.get("time_to_dead", "Unknown")
        })

    return jsonify(events)

# Konfigurační stránka
@app.route('/configuration')
@login_required
def configuration():
    return render_template('configuration.html')

# Kalendářová stránka
@app.route('/PhotoTrackCalendar')
@login_required
def PhotoTrackCalendar():
    return render_template('phototrackcalendar.html')

# Spuštění aplikace
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Vytvoření databáze pro uživatele
    app.run(debug=True)
