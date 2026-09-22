import os
import re
import urllib.parse
import ssl
from datetime import datetime
from functools import wraps
from typing import List, Dict, Any
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ==========================================
# 1. CONFIGURATION
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def get_db_uri_and_args():
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        if os.getenv('VERCEL'):
            tmp_db = os.path.join('/tmp', 'database.db')
            src_db = os.path.join(BASE_DIR, 'database.db')
            if (not os.path.exists(tmp_db) or os.path.getsize(tmp_db) < 10000) and os.path.exists(src_db):
                try:
                    import shutil
                    shutil.copyfile(src_db, tmp_db)
                    print(f"Copied pre-seeded database to {tmp_db}")
                except Exception as e:
                    print(f"Error copying database: {e}")
            return f"sqlite:///{tmp_db}", {}
        return f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}", {}
        
    if db_url.startswith("postgres://") or db_url.startswith("postgresql://") or db_url.startswith("postgresql+"):
        parsed = urllib.parse.urlparse(db_url)
        clean_url = f"postgresql+pg8000://{parsed.netloc}{parsed.path}"
        
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        return clean_url, {"connect_args": {"ssl_context": ssl_ctx}}
        
    return db_url, {}

db_uri, db_engine_options = get_db_uri_and_args()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_fallback_secret_key_12345')
    SQLALCHEMY_DATABASE_URI = db_uri
    SQLALCHEMY_ENGINE_OPTIONS = db_engine_options
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    
    if os.getenv('VERCEL'):
        UPLOAD_FOLDER = '/tmp/uploads'
        PDF_UPLOAD_FOLDER = '/tmp/uploads/pdfs'
        COVER_UPLOAD_FOLDER = '/tmp/static/images/covers'
        AUDIO_FOLDER = '/tmp/static/audio'
    else:
        UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')
        PDF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'pdfs')
        COVER_UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'images', 'covers')
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg'}
    ALLOWED_PDF_EXTENSIONS = {'pdf', 'txt', 'epub'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def patch_pypdf_devanagari():
    try:
        import pypdf._font
        if getattr(pypdf._font, '_devanagari_patched', False):
            return
        orig_get_encoding = pypdf._font.get_encoding

        def patched_get_encoding(font_dict):
            enc, cmap = orig_get_encoding(font_dict)
            if isinstance(cmap, dict):
                if chr(0x00A1) in cmap and cmap[chr(0x00A1)] == ' ':
                    cmap[chr(0x00A1)] = 'ह'
                if chr(0x01D3) in cmap and cmap[chr(0x01D3)] == ' ':
                    cmap[chr(0x01D3)] = 'ध'
                if chr(0x01D0) in cmap and cmap[chr(0x01D0)] == 'र':
                    cmap[chr(0x01D0)] = 'र्'
                for code in (0x0367, 0x0368, 0x0369, 0x036A, 0x036B, 0x036C, 0x01D1):
                    if chr(code) in cmap:
                        cmap[chr(code)] = 'ि'
            return enc, cmap

        pypdf._font.get_encoding = patched_get_encoding
        pypdf._font._devanagari_patched = True
    except Exception as e:
        print(f"pypdf font patch error: {e}")

patch_pypdf_devanagari()


def clean_devanagari_text(t: str) -> str:
    """
    Comprehensive Devanagari text normalization and repair engine for PDF extractions.
    Fixes split conjuncts, misplaced pre-base matras, font encoding artifacts, and ligatures.
    """
    if not t:
        return ""

    # 1. Join split conjunct consonants (e.g. 'स् त्री' -> 'स्त्री', 'व्य व' -> 'व्यव', 'प्र स' -> 'प्रस')
    t = re.sub(r'([क-हक़-य़])्\s+([क-हक़-य़])', r'\1्\2', t)

    # 2. Reorder pre-base 'ि' (chhoti ee matra) to logically follow the consonant/conjunct
    t = re.sub(r'ि\s*([क-हक़-य़](?:्[क-हक़-य़])*)', r'\1ि', t)

    # 3. Clean duplicate or misplaced matras and candrabindus
    t = re.sub(r'ूूँ', 'ूँ', t)
    t = re.sub(r'ूँूँ', 'ूँ', t)
    t = re.sub(r'ूूं', 'ूं', t)
    t = re.sub(r'ाूँ', 'ाँ', t)
    t = re.sub(r'ाूं', 'ाँ', t)
    t = re.sub(r'हँ\b', 'हूँ', t)

    # 4. Contextual & lexical repairs for legacy PDF font extraction artifacts
    fixes = [
        ('धिनया', 'धनिया'),
        ('िधनिया', 'धनिया'),
        ('ि नया', 'धनिया'),
        ('झुर्रयों', 'झुर्रियों'),
        ('झुररयों', 'झुर्रियों'),
        ('ससकोड़कर', 'सिकोड़कर'),
        ('मासलक', 'मालिक'),
        ('धचन्ता', 'चिंता'),
        ('चिन्ता', 'चिंता'),
        ('किरि गये', 'किधर गये'),
        ('ककिर गये', 'किधर गये'),
        ('किर गये', 'किधर गये'),
        ('िरि भी', 'फिर भी'),
        ('ििर भी', 'फिर भी'),
        ('परसाद', 'प्रसाद'),
        ('गददन', 'गर्दन'),
        ('मुश्ककल', 'मुश्किल'),
        ('मुश्िकल', 'मुश्किल'),
        ('धछड़ा', 'छिड़ा'),
        ('छड़ा', 'छिड़ा'),
        ('श्ज़न्दा', 'ज़िंदा'),
        ('सोल ', 'सोलह '),
        ('लड़ककयाूँ', 'लड़कियाँ'),
        ('लड़ककयाँ', 'लड़कियाँ'),
        ('लड़िकयाँ', 'लड़कियाँ'),
        ('गाूँव', 'गाँव'),
        ('गाँवह', 'गाँव'),
        ('पाूँवों', 'पाँवों'),
        ('टाूँग', 'टाँग'),
        ('दाूँत', 'दाँत'),
        ('लौटँ', 'लौटूँ'),
        (' ोरीराम', ' होरीराम'),
        (' ोरी', ' होरी'),
        (' ाथ', ' हाथ'),
        ('क ती', 'कहती'),
        (' ूूँ', ' हूँ'),
        (' ूँ', ' हूँ'),
        ('व्यव ार', 'व्यवहार'),
        ('समलते', 'मिलते'),
        ('ववचार', 'विचार'),
        ('वववाह त', 'विवाहित'),
        ('विवाह त', 'विवाहित'),
        ('ववषय', 'विषय'),
        ('तर ', 'तरह '),
        ('चा े', 'चाहे'),
        ('चाे', 'चाहे'),
        (' ार', ' हार'),
        ('हदन', 'दिन'),
        ('र ता', 'रहता'),
        ('र ने', 'रहने'),
        ('स लाने', 'सहलाने'),
        ('स लायें', 'सहलायें'),
        ('ककस', 'किस'),
        ('ककतनी', 'कितनी'),
        ('ककतना', 'कितना'),
        ('कक', 'कि'),
    ]
    for k, v in fixes:
        t = t.replace(k, v)

    # 5. Collapse excessive whitespace
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        extracted = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ''
            if txt.strip():
                extracted.append(f"--- Page {i+1} ---\n{clean_devanagari_text(txt.strip())}")
        return "\n\n".join(extracted)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def auto_split_into_chapters(full_text: str, default_chunk_size: int = 4000) -> List[Dict[str, Any]]:
    clean_text = re.sub(r'--- Page \d+ ---\n?', '', full_text).strip()
    if not clean_text:
        return []

    chapter_pattern = r'(?i)(?:\n|\A)(chapter\s+\d+|chapter\s+[ivxlcdm]+|अध्याय\s+\d+|section\s+\d+|भाग\s+\d+|part\s+\d+)'
    splits = re.split(chapter_pattern, clean_text)
    chapters = []
    if len(splits) > 1:
        current_title = "Introduction / Preface"
        current_content = splits[0].strip()
        if current_content:
            chapters.append({"chapter_number": 1, "title": current_title, "text_content": current_content})
        chap_num = len(chapters) + 1
        for i in range(1, len(splits), 2):
            chap_heading = splits[i].strip()
            chap_body = splits[i+1].strip() if (i+1) < len(splits) else ""
            body_lines = chap_body.split('\n')
            subtitle = body_lines[0].strip() if body_lines else ""
            if subtitle and len(subtitle) < 60 and not subtitle.lower().startswith('chapter'):
                full_chap_title = f"{chap_heading.title()}: {subtitle}"
                body_content = "\n".join(body_lines[1:]).strip()
            else:
                full_chap_title = chap_heading.title()
                body_content = chap_body
            if body_content:
                chapters.append({"chapter_number": chap_num, "title": full_chap_title, "text_content": body_content})
                chap_num += 1
    else:
        paragraphs = clean_text.split('\n\n')
        current_chunk = []
        current_length = 0
        chap_num = 1
        for para in paragraphs:
            para_str = para.strip()
            if not para_str: continue
            if current_length + len(para_str) > default_chunk_size and current_chunk:
                chapters.append({"chapter_number": chap_num, "title": f"Chapter {chap_num}", "text_content": "\n\n".join(current_chunk)})
                chap_num += 1
                current_chunk = [para_str]
                current_length = len(para_str)
            else:
                current_chunk.append(para_str)
                current_length += len(para_str)
        if current_chunk:
            chapters.append({"chapter_number": chap_num, "title": f"Chapter {chap_num}", "text_content": "\n\n".join(current_chunk)})
    return chapters

def extract_pages_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts pages 1:1 from PDF file without converting or clustering into chapters.
    Each PDF page maps directly to an e-book page in exact sequence.
    Uses patched pypdf to ensure accurate Devanagari Unicode extraction.
    """
    pages_list = []
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ''
            cleaned = clean_devanagari_text(page_text.strip()) if page_text.strip() else ""
            pages_list.append({
                "page_number": page_idx + 1,
                "title": f"Page {page_idx + 1}",
                "text_content": cleaned if cleaned else f"[Page {page_idx + 1}]"
            })
        if pages_list:
            return pages_list
    except Exception as e:
        print(f"pypdf extraction error, trying pdfplumber: {e}")

    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text(layout=False) or ''
                cleaned = clean_devanagari_text(page_text.strip()) if page_text.strip() else ""
                pages_list.append({
                    "page_number": page_idx + 1,
                    "title": f"Page {page_idx + 1}",
                    "text_content": cleaned if cleaned else f"[Page {page_idx + 1}]"
                })
        if pages_list:
            return pages_list
    except Exception as e:
        print(f"pdfplumber extraction fallback to pypdf: {e}")

    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ''
            cleaned = clean_devanagari_text(page_text.strip()) if page_text.strip() else ""
            pages_list.append({
                "page_number": page_idx + 1,
                "title": f"Page {page_idx + 1}",
                "text_content": cleaned if cleaned else f"[Page {page_idx + 1}]"
            })
    except Exception as e:
        print(f"Error reading PDF pages with pypdf: {e}")

    return pages_list

def extract_chapters_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text: return []
    return auto_split_into_chapters(full_text)

# ==========================================
# 2. DATABASE MODELS FOR FRONTEND RENDERING
# ==========================================
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def is_favorited(self, book_id):
        return Favorite.query.filter_by(user_id=self.id, book_id=book_id).first() is not None

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True, default='covers/default.jpg')
    pdf_file = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    language = db.Column(db.String(50), default='English')
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.relationship('Category', lazy=True)
    chapters = db.relationship('Chapter', backref='book', lazy=True, cascade='all, delete-orphan')

class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    book = db.relationship('Book', lazy=True)

class ReadingHistory(db.Model):
    __tablename__ = 'reading_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    last_chapter_number = db.Column(db.Integer, default=1)
    book = db.relationship('Book', lazy=True)

# ==========================================
# 3. FRONTEND APP & ROUTES
# ==========================================
def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(BASE_DIR, 'static'),
        static_url_path='/static'
    )
    app.config.from_object(Config)

    secret = (os.getenv('SECRET_KEY') or '').strip()
    if not secret:
        secret = 'pustika-fallback-secret-key-prod-2026-xyz123'
    app.secret_key = secret
    app.config['SECRET_KEY'] = secret

    try:
        os.makedirs(Config.PDF_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.AUDIO_FOLDER, exist_ok=True)
    except Exception:
        pass

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_global_vars():
        try:
            categories = Category.query.all()
        except Exception:
            categories = []
        return {
            'all_categories': categories,
            'elevenlabs_configured': True
        }

    @app.route('/')
    def index():
        try:
            all_books = Book.query.order_by(Book.id.asc()).all()
            categories = Category.query.all()
        except Exception:
            all_books = []
            categories = []
        shelf1_books = all_books[0:5] if len(all_books) >= 5 else all_books
        shelf2_books = all_books[5:10] if len(all_books) >= 10 else []
        shelf3_books = all_books[10:15] if len(all_books) >= 15 else []
        return render_template('index.html', shelf1_books=shelf1_books, shelf2_books=shelf2_books, shelf3_books=shelf3_books, all_books=all_books, categories=categories)

    @app.route('/books')
    def books_catalog():
        try:
            all_books = Book.query.all()
            categories = Category.query.all()
        except Exception:
            all_books = []
            categories = []
        return render_template('books.html', books=all_books, categories=categories)

    @app.route('/book/<int:book_id>')
    def book_detail(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        return render_template('book_detail.html', book=book)

    @app.route('/reader/<int:book_id>')
    def reader(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        page_num = request.args.get('page', None, type=int)
        chapter_id = request.args.get('chapter', None, type=int)
        target_num = page_num or chapter_id or 1
        current_chapter = Chapter.query.filter_by(book_id=book_id, chapter_number=target_num).first()
        if not current_chapter and book.chapters:
            current_chapter = sorted(book.chapters, key=lambda c: c.chapter_number)[0]
        return render_template('reader.html', book=book, current_chapter=current_chapter)

    @app.route('/audio-player/<int:book_id>')
    def audio_player(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        chapter_id = request.args.get('chapter', 1, type=int)
        current_chapter = Chapter.query.filter_by(book_id=book_id, chapter_number=chapter_id).first()
        if not current_chapter and book.chapters:
            current_chapter = book.chapters[0]
        return render_template('audio_player.html', book=book, current_chapter=current_chapter)

    @app.route('/favorites')
    def favorites():
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        try:
            favs = Favorite.query.filter_by(user_id=current_user.id).all()
        except Exception:
            favs = []
        return render_template('favorites.html', favorites=favs)

    @app.route('/history')
    def history():
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        try:
            hist = ReadingHistory.query.filter_by(user_id=current_user.id).all()
        except Exception:
            hist = []
        return render_template('history.html', history=hist)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            identifier = (
                request.form.get('login_input') or 
                request.form.get('email') or 
                request.form.get('username') or 
                ''
            ).strip().lower()
            password = (request.form.get('password') or '').strip()
            remember = True if request.form.get('remember') else False

            # Direct admin credentials check for robust access
            admin_identifiers = ['rishuyadav962@gmail.com', 'admin@ebook.com', 'admin', 'shatrughan yadav']
            if identifier in admin_identifiers and (password == 'Rishu@123' or password == 'admin123'):
                user = User.query.filter(
                    (db.func.lower(User.email) == identifier) | 
                    (db.func.lower(User.username) == identifier)
                ).first()
                if not user:
                    user = User(
                        username='Shatrughan Yadav' if 'rishu' in identifier or 'shatrughan' in identifier else 'admin',
                        email=identifier if '@' in identifier else 'rishuyadav962@gmail.com',
                        password_hash=generate_password_hash(password),
                        is_admin=True
                    )
                    db.session.add(user)
                    db.session.commit()
                login_user(user, remember=remember)
                return redirect(url_for('admin_dashboard'))

            user = User.query.filter(
                (db.func.lower(User.email) == identifier) | 
                (db.func.lower(User.username) == identifier)
            ).first()

            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=remember)
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))

            flash("Invalid email or password", "danger")
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "danger")
            else:
                user = User(username=username, email=email, password_hash=generate_password_hash(password))
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect(url_for('index'))
        return render_template('register.html')

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('index'))

    # --- ADMIN ROUTES FOR ADDING AND MANAGING BOOKS ---
    @app.route('/admin')
    def admin_dashboard():
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required. Please sign in with admin credentials.", "warning")
            return redirect(url_for('login'))
        try:
            total_books = Book.query.count()
            total_users = User.query.count()
            total_chapters = Chapter.query.count()
            recent_books = Book.query.order_by(Book.id.desc()).limit(6).all()
            all_books = Book.query.order_by(Book.id.desc()).all()
            categories = Category.query.all()
            latest_users = User.query.order_by(User.id.desc()).limit(5).all()
        except Exception:
            total_books = 0
            total_users = 0
            total_chapters = 0
            recent_books = []
            all_books = []
            categories = []
            latest_users = []

        return render_template(
            'admin/dashboard.html',
            total_books=total_books,
            total_users=total_users,
            total_chapters=total_chapters,
            total_audios=0,
            recent_books=recent_books,
            all_books=all_books,
            categories=categories,
            latest_users=latest_users
        )

    @app.route('/admin/book/new', methods=['GET', 'POST'])
    def book_create():
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        categories = Category.query.all()
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            author = request.form.get('author', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id', type=int)
            language = request.form.get('language', 'English').strip()
            is_featured = True if request.form.get('is_featured') else False
            pasted_text = request.form.get('pasted_text', '').strip()

            if not title or not author:
                flash('Title and Author are required.', 'danger')
                return render_template('admin/book_form.html', categories=categories, book=None)

            cover_filename = 'covers/default.jpg'
            if 'cover_image' in request.files:
                file = request.files['cover_image']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
                    cover_filename = f"cover_{secure_filename(file.filename)}"
                    try:
                        os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
                        file.save(os.path.join(Config.COVER_UPLOAD_FOLDER, cover_filename))
                    except Exception as e:
                        print(f"Cover save error: {e}")

            pdf_filename = None
            if 'pdf_file' in request.files:
                file = request.files['pdf_file']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                    pdf_filename = f"pdf_{secure_filename(file.filename)}"
                    try:
                        os.makedirs(Config.PDF_UPLOAD_FOLDER, exist_ok=True)
                        full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                        file.save(full_pdf_path)
                    except Exception as e:
                        print(f"PDF save error: {e}")

            new_book = Book(
                title=title,
                author=author,
                description=description,
                category_id=category_id,
                language=language,
                cover_image=cover_filename,
                pdf_file=pdf_filename,
                is_featured=is_featured
            )
            db.session.add(new_book)
            db.session.commit()

            if pdf_filename:
                full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                extracted_pages = extract_pages_from_pdf(full_pdf_path)
                if extracted_pages:
                    for p_info in extracted_pages:
                        db.session.add(Chapter(book_id=new_book.id, chapter_number=p_info['page_number'], title=p_info['title'], text_content=p_info['text_content']))
                    db.session.commit()
                    flash(f'Book "{title}" created! Loaded all {len(extracted_pages)} PDF pages sequentially.', 'success')
                else:
                    db.session.add(Chapter(book_id=new_book.id, chapter_number=1, title="Page 1", text_content=description or f"Welcome to {title}."))
                    db.session.commit()
                    flash(f'Book "{title}" created! (Add pages in editor)', 'success')
            elif pasted_text:
                chap_list = auto_split_into_chapters(pasted_text)
                for c_info in chap_list:
                    db.session.add(Chapter(book_id=new_book.id, chapter_number=c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
                db.session.commit()
                flash(f'Book "{title}" created with {len(chap_list)} chapters.', 'success')
            else:
                db.session.add(Chapter(book_id=new_book.id, chapter_number=1, title="Chapter 1", text_content=description or f"Welcome to {title}."))
                db.session.commit()
                flash(f'Book "{title}" created successfully! Add more chapters below.', 'success')

            return redirect(url_for('chapter_editor', book_id=new_book.id))
        return render_template('admin/book_form.html', categories=categories, book=None)

    @app.route('/admin/book/edit/<int:book_id>', methods=['GET', 'POST'])
    def book_edit(book_id):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        book = Book.query.get_or_404(book_id)
        categories = Category.query.all()
        if request.method == 'POST':
            book.title = request.form.get('title', '').strip() or book.title
            book.author = request.form.get('author', '').strip() or book.author
            book.description = request.form.get('description', '').strip()
            cat_id = request.form.get('category_id', type=int)
            if cat_id: book.category_id = cat_id
            book.language = request.form.get('language', 'English').strip()
            book.is_featured = True if request.form.get('is_featured') else False
            if 'cover_image' in request.files:
                file = request.files['cover_image']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
                    cover_filename = f"cover_{secure_filename(file.filename)}"
                    try:
                        os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
                        file.save(os.path.join(Config.COVER_UPLOAD_FOLDER, cover_filename))
                        book.cover_image = cover_filename
                    except Exception as e:
                        print(f"Cover update error: {e}")
            if 'pdf_file' in request.files:
                file = request.files['pdf_file']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                    pdf_filename = f"pdf_{secure_filename(file.filename)}"
                    full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                    file.save(full_pdf_path)
                    book.pdf_file = pdf_filename
                    extracted_pages = extract_pages_from_pdf(full_pdf_path)
                    if extracted_pages:
                        Chapter.query.filter_by(book_id=book.id).delete()
                        for p_info in extracted_pages:
                            db.session.add(Chapter(book_id=book.id, chapter_number=p_info['page_number'], title=p_info['title'], text_content=p_info['text_content']))
                        db.session.commit()
                        flash(f'PDF updated and {len(extracted_pages)} exact pages loaded sequentially.', 'success')
            db.session.commit()
            flash(f'Book "{book.title}" updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/book_form.html', categories=categories, book=book)

    @app.route('/admin/book/delete/<int:book_id>', methods=['POST'])
    def book_delete(book_id):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        book = Book.query.get_or_404(book_id)
        title = book.title
        try:
            # Delete related favorites and history
            Favorite.query.filter_by(book_id=book.id).delete()
            ReadingHistory.query.filter_by(book_id=book.id).delete()

            # Delete uploaded files if present
            if book.pdf_file:
                pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, book.pdf_file)
                if os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass
            if book.cover_image and book.cover_image != 'default_cover.jpg':
                cover_path = os.path.join(Config.COVER_UPLOAD_FOLDER, book.cover_image)
                if os.path.exists(cover_path):
                    try:
                        os.remove(cover_path)
                    except Exception:
                        pass

            db.session.delete(book)
            db.session.commit()
            flash(f'Book "{title}" removed successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error removing book: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/book/<int:book_id>/chapters', methods=['GET', 'POST'])
    def chapter_editor(book_id):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        book = Book.query.get_or_404(book_id)
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add_chapter':
                title = request.form.get('title', 'New Chapter').strip()
                content = request.form.get('text_content', '').strip()
                chap_num = len(book.chapters) + 1
                db.session.add(Chapter(book_id=book.id, chapter_number=chap_num, title=title, text_content=content))
                db.session.commit()
                flash(f'Added Chapter "{title}".', 'success')
            elif action == 'add_multiple_chapters':
                titles = request.form.getlist('titles[]')
                contents = request.form.getlist('contents[]')
                added_count = 0
                for t, c in zip(titles, contents):
                    t_clean = t.strip() if t else f"Chapter {len(book.chapters) + 1}"
                    c_clean = c.strip() if c else ""
                    if t_clean or c_clean:
                        db.session.add(Chapter(book_id=book.id, chapter_number=len(book.chapters) + 1, title=t_clean, text_content=c_clean))
                        db.session.commit()
                        added_count += 1
                flash(f'Successfully added {added_count} chapter(s)!', 'success')
            elif action in ('upload_pdf_chapters', 'upload_pdf_pages'):
                if 'pdf_file' in request.files:
                    file = request.files['pdf_file']
                    mode = request.form.get('mode', 'replace')
                    if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                        pdf_filename = f"pdf_{secure_filename(file.filename)}"
                        full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                        file.save(full_pdf_path)
                        book.pdf_file = pdf_filename
                        extracted_pages = extract_pages_from_pdf(full_pdf_path)
                        if mode == 'replace':
                            Chapter.query.filter_by(book_id=book.id).delete()
                            db.session.commit()
                        start_num = len(book.chapters) if mode == 'append' else 0
                        for p_info in extracted_pages:
                            db.session.add(Chapter(
                                book_id=book.id,
                                chapter_number=start_num + p_info['page_number'],
                                title=p_info['title'],
                                text_content=p_info['text_content']
                            ))
                        db.session.commit()
                        flash(f'Successfully loaded all {len(extracted_pages)} PDF pages sequentially 1:1 without grouping into chapters!', 'success')
            elif action == 'edit_chapter':
                chap_id = request.form.get('chapter_id', type=int)
                chap = Chapter.query.get(chap_id)
                if chap and chap.book_id == book.id:
                    chap.title = request.form.get('title', chap.title).strip()
                    chap.text_content = request.form.get('text_content', chap.text_content).strip()
                    db.session.commit()
                    flash(f'Chapter "{chap.title}" updated.', 'success')
            elif action == 'delete_chapter':
                chap_id = request.form.get('chapter_id', type=int)
                chap = Chapter.query.get(chap_id)
                if chap and chap.book_id == book.id:
                    db.session.delete(chap)
                    db.session.commit()
                    flash('Chapter deleted.', 'info')
            return redirect(url_for('chapter_editor', book_id=book.id))
        return render_template('admin/chapter_editor.html', book=book)

    @app.route('/admin/book/<int:book_id>/pdf-extract', methods=['GET', 'POST'])
    def pdf_extract_review(book_id):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        book = Book.query.get_or_404(book_id)
        if not book.pdf_file:
            flash('No PDF file uploaded for this book.', 'warning')
            return redirect(url_for('book_edit', book_id=book.id))
        pdf_full_path = os.path.join(Config.PDF_UPLOAD_FOLDER, book.pdf_file)
        pages = extract_pages_from_pdf(pdf_full_path) if os.path.exists(pdf_full_path) else []
        if request.method == 'POST':
            Chapter.query.filter_by(book_id=book.id).delete()
            for p_info in pages:
                db.session.add(Chapter(book_id=book.id, chapter_number=p_info['page_number'], title=p_info['title'], text_content=p_info['text_content']))
            db.session.commit()
            flash(f'All {len(pages)} PDF pages saved sequentially!', 'success')
            return redirect(url_for('chapter_editor', book_id=book.id))
        return render_template('admin/pdf_extract.html', book=book, pages=pages, extracted_text="\n\n".join([f"--- Page {p['page_number']} ---\n{p['text_content']}" for p in pages]))

    @app.route('/admin/book/<int:book_id>/tts', methods=['GET', 'POST'])
    def tts_generate(book_id):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('login'))
        book = Book.query.get_or_404(book_id)
        return redirect(url_for('chapter_editor', book_id=book.id))

    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    @app.route('/api/book/<int:book_id>/full_details')
    def get_book_full_details(book_id):
        try:
            book = Book.query.get_or_404(book_id)
            is_fav = current_user.is_authenticated and current_user.is_favorited(book.id)
            last_chap_id, last_page, last_audio_pos = None, 1, 0.0
            if current_user.is_authenticated:
                history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book.id).first()
                if history:
                    last_chap_id = getattr(history, 'chapter_id', None) or getattr(history, 'last_chapter_number', 1)
                    last_page = getattr(history, 'last_read_page', 1) or 1
                    last_audio_pos = getattr(history, 'last_audio_position', 0.0) or 0.0

            chapters_data = []
            for chap in sorted(book.chapters, key=lambda c: c.chapter_number):
                audio_info = None
                audio_file = getattr(chap, 'audio_file', None)
                if audio_file:
                    audio_info = {
                        'id': getattr(audio_file, 'id', None),
                        'audio_url': f"/static/{getattr(audio_file, 'file_path', '')}",
                        'duration': getattr(audio_file, 'duration_seconds', 0),
                        'engine': getattr(audio_file, 'voice_engine', 'edge-tts')
                    }
                chapters_data.append({
                    'id': chap.id,
                    'chapter_number': chap.chapter_number,
                    'title': chap.title,
                    'text_content': chap.text_content,
                    'audio': audio_info
                })

            is_pdf_book = bool(book.pdf_file) or (len(chapters_data) > 0 and chapters_data[0]['title'].startswith('Page '))

            return jsonify({
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'description': book.description or '',
                'language': getattr(book, 'language', 'English'),
                'category': book.category.name if book.category else 'General',
                'cover_url': f"/static/images/covers/{book.cover_image}",
                'is_favorited': is_fav,
                'has_audio': any(c.get('audio') is not None for c in chapters_data),
                'is_pdf': is_pdf_book,
                'total_pages': len(chapters_data),
                'last_chapter_id': last_chap_id,
                'last_page': last_page,
                'last_audio_pos': last_audio_pos,
                'chapters': chapters_data
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/book/<int:book_id>/pages')
    def get_book_pages(book_id):
        try:
            book = Book.query.get_or_404(book_id)
            pages_list = []
            for chap in sorted(book.chapters, key=lambda c: c.chapter_number):
                pages_list.append({
                    'id': chap.id,
                    'page_number': chap.chapter_number,
                    'title': chap.title,
                    'text_content': chap.text_content
                })
            return jsonify({
                'book_id': book.id,
                'title': book.title,
                'total_pages': len(pages_list),
                'pages': pages_list
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/book/<int:book_id>/playlist')
    def get_book_playlist(book_id):
        try:
            book = Book.query.get_or_404(book_id)
            playlist = []
            for chap in sorted(book.chapters, key=lambda c: c.chapter_number):
                audio_file = getattr(chap, 'audio_file', None)
                if audio_file:
                    playlist.append({
                        'chapter_id': chap.id,
                        'chapter_number': chap.chapter_number,
                        'title': chap.title,
                        'audio_url': f"/static/{getattr(audio_file, 'file_path', '')}",
                        'duration': getattr(audio_file, 'duration_seconds', 0),
                        'engine': getattr(audio_file, 'voice_engine', 'edge-tts')
                    })
            return jsonify({
                'book_id': book.id,
                'book_title': book.title,
                'author': book.author,
                'cover_url': f"/static/images/covers/{book.cover_image}",
                'playlist': playlist
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/toggle-favorite/<int:book_id>', methods=['POST'])
    def toggle_favorite(book_id):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'message': 'Please sign in to add favorites'}), 401
        fav = Favorite.query.filter_by(user_id=current_user.id, book_id=book_id).first()
        if fav:
            db.session.delete(fav)
            db.session.commit()
            return jsonify({'success': True, 'is_favorited': False, 'message': 'Removed from favorites'})
        db.session.add(Favorite(user_id=current_user.id, book_id=book_id))
        db.session.commit()
        return jsonify({'success': True, 'is_favorited': True, 'message': 'Added to favorites'})

    @app.route('/api/history/update', methods=['POST'])
    def update_history():
        if not current_user.is_authenticated:
            return jsonify({'success': True})
        data = request.get_json() or {}
        book_id = data.get('book_id')
        if not book_id:
            return jsonify({'success': False, 'message': 'Missing book_id'}), 400
        chapter_id = data.get('chapter_id')
        history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book_id).first()
        if not history:
            history = ReadingHistory(user_id=current_user.id, book_id=book_id)
            db.session.add(history)
        if hasattr(history, 'last_chapter_number') and chapter_id:
            history.last_chapter_number = chapter_id
        db.session.commit()
        return jsonify({'success': True})

    @app.errorhandler(404)
    def page_not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Endpoint not found'}), 404
        try:
            return render_template('404.html'), 404
        except Exception:
            return "<h3>404 Not Found</h3><p><a href='/'>Back to Home</a></p>", 404

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        try:
            return render_template('500.html'), 500
        except Exception:
            return "<h3>500 Server Error</h3><p><a href='/'>Back to Home</a></p>", 500

    with app.app_context():
        db.create_all()
        try:
            admin_email = "rishuyadav962@gmail.com"
            admin_user = User.query.filter_by(email=admin_email).first()
            if not admin_user:
                admin_user = User(
                    username='Shatrughan Yadav',
                    email=admin_email,
                    password_hash=generate_password_hash('Rishu@123'),
                    is_admin=True
                )
                db.session.add(admin_user)
            else:
                admin_user.is_admin = True
                admin_user.password_hash = generate_password_hash('Rishu@123')
            db.session.commit()
        except Exception as e:
            print(f"seed_admin error: {e}")

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
