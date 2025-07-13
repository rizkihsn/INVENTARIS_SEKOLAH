from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import io
import os
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl import Workbook
from openpyxl.styles import Font

app = Flask(__name__)
app.secret_key = 'rahasia'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), default='staf')
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Barang(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kode = db.Column(db.String(10), nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    kondisi = db.Column(db.String(50), nullable=False)
    lokasi = db.Column(db.String(100), nullable=False)
    tanggal = db.Column(db.String(50), nullable=False)
    gambar = db.Column(db.String(200), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Akses hanya untuk admin.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('beranda.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan')
            return redirect(url_for('register'))
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registrasi berhasil! Silakan login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Username atau password salah')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    keyword = request.args.get('keyword', '')
    if keyword:
        barang = Barang.query.filter(Barang.user_id==current_user.id, Barang.nama.contains(keyword)).all()
    else:
        barang = Barang.query.filter_by(user_id=current_user.id).all()
    total = sum([b.jumlah for b in barang])
    return render_template('dashboard.html', barang=barang, total=total)

@app.route('/hapus_semua', methods=['POST'])
@login_required
def hapus_semua():
    Barang.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash("Semua barang berhasil dihapus.")
    return redirect(url_for('dashboard'))

@app.route('/tambah', methods=['GET', 'POST'])
@login_required
def tambah():
    if request.method == 'POST':
        kode = request.form['kode']
        nama = request.form['nama']
        jumlah = int(request.form['jumlah'])
        kondisi = request.form['kondisi']
        lokasi = request.form['lokasi']
        tanggal = datetime.now().strftime('%Y-%m-%d')
        gambar = request.files['gambar']
        gambar_filename = gambar.filename
        gambar_path = os.path.join(app.config['UPLOAD_FOLDER'], gambar_filename)
        gambar.save(gambar_path)

        barang = Barang(kode=kode, nama=nama, jumlah=jumlah, kondisi=kondisi, lokasi=lokasi, tanggal=tanggal, gambar=gambar_filename, user_id=current_user.id)
        db.session.add(barang)
        db.session.commit()
        flash('Barang berhasil ditambahkan')
        return redirect(url_for('dashboard'))
    return render_template('tambah_barang.html')

@app.route('/hapus/<int:id>')
@login_required
def hapus(id):
    barang = Barang.query.get_or_404(id)
    if barang.user_id != current_user.id:
        flash('Tidak diizinkan')
        return redirect(url_for('dashboard'))
    db.session.delete(barang)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    barang = Barang.query.get_or_404(id)
    if barang.user_id != current_user.id:
        flash('Tidak diizinkan')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        barang.kode = request.form['kode']
        barang.nama = request.form['nama']
        barang.jumlah = int(request.form['jumlah'])
        barang.kondisi = request.form['kondisi']
        barang.lokasi = request.form['lokasi']
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit_barang.html', barang=barang)

@app.route('/laporan', methods=['GET', 'POST'])
@login_required
def laporan():
    barang = []

    if request.method == 'POST':
        bulan = request.form.get('bulan')  # contoh: '2025-07'
        if bulan:
            barang = Barang.query.filter(
                Barang.user_id == current_user.id,
                Barang.tanggal.like(f"{bulan}%")
            ).all()
    return render_template('laporan.html', barang=barang)


@app.route('/download_pdf')
@login_required
def download_pdf():
    barang = Barang.query.filter_by(user_id=current_user.id).all()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Laporan Inventaris Barang", styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Kode', 'Nama', 'Jumlah', 'Kondisi', 'Lokasi', 'Tanggal']]
    for b in barang:
        data.append([b.kode, b.nama, b.jumlah, b.kondisi, b.lokasi, b.tanggal])
    table = Table(data, repeatRows=1, colWidths=[50, 100, 50, 60, 100, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgreen),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='laporan.pdf', mimetype='application/pdf')

@app.route('/download_excel')
@login_required
def download_excel():
    barang = Barang.query.filter_by(user_id=current_user.id).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan Inventaris"
    headers = ['Kode', 'Nama', 'Jumlah', 'Kondisi', 'Lokasi', 'Tanggal']
    ws.append(headers)
    for b in barang:
        ws.append([b.kode, b.nama, b.jumlah, b.kondisi, b.lokasi, b.tanggal])
    for col in ws.columns:
        max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2
    for cell in ws["1:1"]:
        cell.font = Font(bold=True)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='laporan.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/pengguna')
@login_required
@admin_required
def pengguna():
    users = User.query.all()
    return render_template('pengguna.html', users=users)

@app.route('/pengguna/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def pengguna_detail(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form['username']
        user.role = request.form['role']
        user.status = True if request.form.get('status') == 'aktif' else False
        db.session.commit()
        flash('Data pengguna diperbarui.')
        return redirect(url_for('pengguna'))
    return render_template('pengguna_detail.html', user=user)

@app.route('/ganti_password', methods=['GET', 'POST'])
@login_required
def ganti_password():
    if request.method == 'POST':
        old = request.form['old_password']
        new = request.form['new_password']
        if check_password_hash(current_user.password, old):
            current_user.password = generate_password_hash(new)
            db.session.commit()
            flash("Password berhasil diganti.")
            return redirect(url_for('dashboard'))
        flash("Password lama salah.")
    return render_template('ganti_password.html')

@app.route('/muat_data_contoh')
@login_required
def muat_data_contoh():
    if Barang.query.filter_by(user_id=current_user.id, kode='01').first():
        flash('Data contoh sudah dimuat.')
        return redirect(url_for('dashboard'))

    contoh_data = [
        ('01', 'Meja', 10, 'Baik', 'Ruang Kelas'),
        ('02', 'Proyektor', 2, 'Rusak', 'Lab Komputer'),
        ('03', 'Lemari Arsip', 3, 'Baik', 'Kantor Guru'),
        ('04', 'Laptop', 5, 'Baik', 'Lab Komputer'),
        ('05', 'Kursi Lipat', 20, 'Baik', 'Aula')
    ]
    tanggal = datetime.now().strftime('%Y-%m-%d')
    for kode, nama, jumlah, kondisi, lokasi in contoh_data:
        barang = Barang(
            kode=kode, nama=nama, jumlah=jumlah,
            kondisi=kondisi, lokasi=lokasi,
            tanggal=tanggal, user_id=current_user.id
        )
        db.session.add(barang)
    db.session.commit()
    flash('Data contoh berhasil dimuat.')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password=generate_password_hash('admin123'), role='admin')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)