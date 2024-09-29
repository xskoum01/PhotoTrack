from datetime import datetime
from flask import Flask, request, flash, redirect, url_for, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

app = Flask(__name__) #hlavni objekt aplikace

#pripojeni k azure storage
connect_str = "DefaultEndpointsProtocol=https;AccountName=vsmphototrackstorage;AccountKey=KNjm7pyqb7yAqBX8ztxmMrxoD0TafLaQj+BLX+tS4AvNFZkd4+FVOU4PbpXYIv2gQvoSsM6q2LUt+AStfj+N7w==;EndpointSuffix=core.windows.net"
blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_name = "photos"

#vytvoreni kontejneru
container_client = blob_service_client.get_container_client(container_name)
try:
    container_client.create_container()
except ResourceExistsError:
    pass

#konfigurace databaze
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/users.db' #umisteni databaze
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'

#inicializace databazoveho objektu
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150), nullable=False)  #nazev souboru fotografie
    blob_url = db.Column(db.String(500), nullable=False)  #URL adresa v azure blob storage
    date_taken = db.Column(db.DateTime, nullable=False)  #datum porizení
    battery_level = db.Column(db.String(50), nullable=False)  #stav baterie
    charging_status = db.Column(db.String(50), nullable=False)  #stav dobijeni
    time_to_dead = db.Column(db.String(50), nullable=False) #cas do vybiti baterky

#nacitani uzivatelu z db
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        #vyhledani uzivatele v db
        user = User.query.filter_by(username=username).first()

        if user and user.password_hash == password:
            login_user(user)
            flash('Successfully logged in', 'Success')
            return redirect(url_for('PhotoTrackCalendar'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/upload', methods=['POST'])
def upload_photo():
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    #ulozeni souboru do azure storage
    container_name = "photos"
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=file.filename)
    blob_client.upload_blob(file.read(), overwrite=True)

    #ulozeni url obrazku v azure ulozisti
    blob_url = blob_client.url


    #ziskani dalsich dat - stav baterie a dobijeni
    battery_level = request.form.get('battery_level', 'Unknown')
    charging_status = request.form.get('charging_status', 'Unknown')
    time_to_dead = request.form.get('time_to_dead', 'Unknown')

    #ulozeni informaci do db
    date_taken = datetime.now()

    #objekt Photo a jeho vlastnostni
    new_photo = Photo(
        filename=file.filename,
        blob_url=blob_url,
        date_taken=date_taken,
        battery_level=battery_level,
        charging_status=charging_status,
        time_to_dead=time_to_dead
    )
    db.session.add(new_photo)
    db.session.commit()

    return "File and data uploaded successfully", 200

@app.route('/get_events')
def get_events():
    photos = Photo.query.all()
    events = []
    for photo in photos:
        events.append({
            'title': photo.filename,
            'start': photo.date_taken.strftime("%Y-%m-%dT%H:%M:%S"),
            'image': photo.blob_url,
            'battery_level': photo.battery_level,
            'charging_status': photo.charging_status,
            'time_to_dead': photo.time_to_dead
        })
    print(events)  #ladici radek pro kontrolu
    return jsonify(events)


@app.route('/PhotoTrackCalendar')
@login_required
def PhotoTrackCalendar():
    photos = Photo.query.all()  #Ziskani vsech fotografii z databaze
    return render_template('phototrackcalendar.html', photos=photos)

if __name__ == '__main__':
    with app.app_context():
        #vytvoreni tabulek v databazi, pokud jeste neexistuji
        db.create_all()
    app.run(debug=True)
