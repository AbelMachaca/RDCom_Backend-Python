from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from simple_salesforce import Salesforce
from datetime import datetime
from sqlalchemy import func
from dotenv import load_dotenv

from flask_cors import CORS



import os

load_dotenv()

app = Flask(__name__)
CORS(app)


# class Config:
#     DB_USERNAME = os.getenv('DB_USERNAME', 'root')
#     DB_PASSWORD = os.getenv('DB_PASSWORD', 'root')
#     DB_NAME = os.getenv('DB_NAME', 'phonestore')
#     DB_HOST = os.getenv('DB_HOST', 'localhost')
#     DB_PORT = os.getenv('DB_PORT', 3306)
#     DB_DIALECT = os.getenv('DB_DIALECT', 'mysql')


# # Configura la conexión a la base de datos MySQL
# app.config['SQLALCHEMY_DATABASE_URI'] = f"{Config.DB_DIALECT}://{Config.DB_USERNAME}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False



# Configuración de SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:root@localhost/rdcom_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)








# Cargar credenciales de Salesforce desde variables de entorno
sf = Salesforce(
    username=os.getenv('SF_USERNAME'), 
    password=os.getenv('SF_PASSWORD'), 
    security_token=os.getenv('SF_SECURITY_TOKEN'), 
    domain='login'
)





class Pacientes(db.Model):
    __tablename__ = 'pacientes'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    edad = db.Column(db.Integer, nullable=False)
    enfermedad = db.Column(db.String(255), nullable=False)
    sf_id = db.Column(db.String(18), nullable=False)
    visitas = db.relationship('Visita', backref='paciente', lazy=True)
    tratamientos = db.relationship('Tratamiento', backref='paciente', lazy=True)

class Visita(db.Model):
    __tablename__ = 'visitas'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)

class Tratamiento(db.Model):
    __tablename__ = 'tratamientos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=False)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)
    sf_id = db.Column(db.String(18), nullable=False)
with app.app_context():
    # Crea todas las tablas en la base de datos
    db.create_all()

@app.route('/pacientes', methods=['GET'])
def get_pacientes():
    pacientes = Pacientes.query.all()
    pacientes_list = [{'id': p.id, 'nombre': p.nombre, 'edad': p.edad, 'enfermedad': p.enfermedad} for p in pacientes]
    return jsonify(pacientes_list)

@app.route('/paciente', methods=['POST'])
def add_paciente():
    data = request.json
    sf_response = sf.Paciente__c.create({
        'Name': data['nombre'], 
        'Edad__c': data['edad'], 
        'Enfermedad__c': data['enfermedad']
    })
    new_paciente = Pacientes(
        nombre=data['nombre'], 
        edad=data['edad'], 
        enfermedad=data['enfermedad'],
        sf_id=sf_response['id']
    )
    db.session.add(new_paciente)
    db.session.commit()
    return jsonify({"status": "Paciente creado"}), 201

@app.route('/paciente/<int:id>', methods=['GET'])
def get_paciente(id):
    paciente = Pacientes.query.get(id)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    paciente_data = {
        'id': paciente.id,
        'nombre': paciente.nombre,
        'edad': paciente.edad,
        'enfermedad': paciente.enfermedad,
        'tratamientos': [{'id': t.id, 'nombre': t.nombre, 'descripcion': t.descripcion, 'fecha_inicio': t.fecha_inicio, 'fecha_fin': t.fecha_fin} for t in paciente.tratamientos],
        'sf_id': paciente.sf_id
    }
    return jsonify(paciente_data)

@app.route('/tratamientos/<int:paciente_id>', methods=['GET'])
def get_tratamientos(paciente_id):
    tratamientos = Tratamiento.query.filter_by(paciente_id=paciente_id).all()
    tratamientos_list = [{'id': t.id, 'nombre': t.nombre, 'descripcion': t.descripcion, 'fecha_inicio': t.fecha_inicio, 'fecha_fin': t.fecha_fin} for t in tratamientos]
    return jsonify(tratamientos_list)


@app.route('/tratamiento', methods=['POST'])
def add_tratamiento():
    data = request.json
    paciente_sf_record = sf.Paciente__c.get(data['paciente_id'])
    paciente_sf_id = paciente_sf_record['Id'] 
    #print("trat devuelt", paciente_sf_record)

     # Buscar el ID local del paciente en la base de datos
    paciente_local = Pacientes.query.filter_by(sf_id=paciente_sf_id).first()
    if not paciente_local:
        return jsonify({"error": "Paciente no encontrado en la base de datos local"}), 404


    sf_response = sf.Tratamiento__c.create({
        'Name': data['nombre'],
        'Descripcion__c': data['descripcion'],
        'Fecha_Inicio__c': data['fecha_inicio'],
        'Fecha_Fin__c': data['fecha_fin'],
        'Paciente__c': paciente_sf_id# Asumiendo que el ID de Salesforce del paciente es almacenado en la base de datos.
    })
    
    new_tratamiento = Tratamiento(
        nombre=data['nombre'], 
        descripcion=data['descripcion'],
        fecha_inicio=data['fecha_inicio'],
        fecha_fin=data['fecha_fin'],
        paciente_id=paciente_local.id,
        sf_id=paciente_sf_id
    )
    db.session.add(new_tratamiento)
    db.session.commit()
    return jsonify({"status": "Tratamiento creado"}), 201



@app.route('/grafico-tratamientos', methods=['GET'])
def grafico_tratamientos():
    tratamientos_por_paciente = db.session.query(
        Pacientes, db.func.count(Tratamiento.id).label('tratamientos')
    ).join(Tratamiento).group_by(Pacientes.id).all()

    data = {
        'labels': [p.nombre for p, t in tratamientos_por_paciente],
        'data': [t for p, t in tratamientos_por_paciente]
    }
    return jsonify(data)



@app.route('/duracion-promedio-tratamientos', methods=['GET'])
def duracion_promedio_tratamientos():
    # Obtener la duración promedio de los tratamientos en días usando SQLALchemy
    duracion_promedio = db.session.query(func.avg(func.datediff(Tratamiento.fecha_fin, Tratamiento.fecha_inicio))).scalar()

    # Convertir la duración promedio a un número entero de días
    duracion_promedio_dias = int(duracion_promedio) if duracion_promedio is not None else 0

    return jsonify({"duracion_promedio_dias": duracion_promedio_dias})



@app.route('/visita', methods=['POST'])
def add_visita():
    data = request.json
    new_visita = Visita(fecha=data['fecha'], descripcion=data['descripcion'], paciente_id=data['paciente_id'])
    db.session.add(new_visita)
    db.session.commit()
    return jsonify({"status": "Visita creada"}), 201



@app.route('/visitas/<int:paciente_id>', methods=['GET'])
def get_visitas(paciente_id):
    visitas = Visita.query.filter_by(paciente_id=paciente_id).all()
    visitas_list = [{'id': v.id, 'fecha': v.fecha, 'descripcion': v.descripcion} for v in visitas]
    return jsonify(visitas_list)




@app.route('/paciente/<paciente_id>', methods=['DELETE'])
def delete_paciente(paciente_id):
    try:
        sf.Paciente__c.delete(paciente_id)
        return jsonify({"status": "Paciente eliminado correctamente"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True)
