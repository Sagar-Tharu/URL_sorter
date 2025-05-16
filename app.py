from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, URL, User, ClickLog
from datetime import datetime, timedelta
import string, random, qrcode
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
import requests
from user_agents import parse
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/qr_codes'

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Create database tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Generate a random short URL
def generate_short_url(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))

def generate_qr_code(short_url):
    try:
        # Ensure the upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Generate the full URL for the QR code
        full_url = request.host_url.rstrip('/') + '/' + short_url
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(full_url)
        qr.make(fit=True)

        # Create an image from the QR Code
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Save the image
        filename = f"qr_{short_url}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        qr_image.save(filepath)
        
        print(f"QR code generated successfully: {filename}")
        return filename
    except Exception as e:
        print(f"Error generating QR code: {str(e)}")
        return None

def get_location_data(ip_address):
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_address}')
        data = response.json()
        return {
            'country': data.get('countryCode'),
            'city': data.get('city')
        }
    except:
        return {'country': None, 'city': None}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            original_url = request.form['original_url']
            custom_alias = request.form.get('custom_alias')
            title = request.form.get('title')
            description = request.form.get('description')
            tags = request.form.get('tags')
            expiry_days = request.form.get('expiry_days')
            password = request.form.get('password')
            
            print(f"Creating URL with original_url: {original_url}")
            
            # Check if custom alias is provided and unique
            if custom_alias:
                if URL.query.filter_by(short_url=custom_alias).first():
                    flash("Alias already taken, choose another one.", "error")
                    return redirect(url_for('index'))
                short_url = custom_alias
                is_custom = True
            else:
                short_url = generate_short_url()
                is_custom = False
            
            print(f"Generated short_url: {short_url}")

            # Generate QR code
            qr_code = generate_qr_code(short_url)
            print(f"Generated QR code: {qr_code}")

            # Create URL entry
            new_url = URL(
                original_url=original_url,
                short_url=short_url,
                title=title,
                description=description,
                tags=tags,
                is_custom=is_custom,
                qr_code=qr_code,
                ip_address=request.remote_addr,
                user_id=current_user.id if current_user.is_authenticated else None
            )

            if password:
                new_url.password = generate_password_hash(password)

            if expiry_days:
                new_url.expiry_date = datetime.utcnow() + timedelta(days=int(expiry_days))

            print("Adding URL to database...")
            db.session.add(new_url)
            db.session.commit()
            print("URL added successfully")

            return render_template('short_url.html', url=new_url)
        except Exception as e:
            print(f"Error creating URL: {str(e)}")
            flash("An error occurred while creating the URL. Please try again.", "error")
            return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/<short_url>')
def redirect_to_url(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first_or_404()
    
    # Check if URL is active
    if not url_entry.is_active:
        flash("This URL has been deactivated.", "error")
        return redirect(url_for('index'))
    
    # Check if URL has expired
    if url_entry.expiry_date and url_entry.expiry_date < datetime.utcnow():
        flash("This URL has expired.", "error")
        return redirect(url_for('index'))
    
    # Check if URL is password protected
    if url_entry.password:
        if not session.get(f'url_{short_url}_verified'):
            return redirect(url_for('verify_password', short_url=short_url))

    # Log the click
    user_agent = parse(request.user_agent.string)
    location_data = get_location_data(request.remote_addr)
    
    click_log = ClickLog(
        url_id=url_entry.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        referrer=request.referrer,
        country=location_data['country'],
        city=location_data['city'],
        device_type=user_agent.device.family,
        browser=user_agent.browser.family
    )
    
    db.session.add(click_log)
    url_entry.click_count += 1
    url_entry.last_accessed = datetime.utcnow()
    db.session.commit()

    return redirect(url_entry.original_url)

@app.route('/verify_password/<short_url>', methods=['GET', 'POST'])
def verify_password(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first_or_404()
    
    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(url_entry.password, password):
            session[f'url_{short_url}_verified'] = True
            return redirect(url_for('redirect_to_url', short_url=short_url))
        else:
            flash("Incorrect password.", "error")
    
    return render_template('verify_password.html', short_url=short_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash("Registration successful! Please login.", "success")
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('dashboard'))
        
        flash("Invalid username or password.", "error")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_urls = URL.query.filter_by(user_id=current_user.id).order_by(URL.created_at.desc()).all()
    return render_template('dashboard.html', urls=user_urls)

@app.route('/url/<short_url>/stats')
@login_required
def url_stats(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first_or_404()
    if url_entry.user_id != current_user.id:
        flash("You don't have permission to view these stats.", "error")
        return redirect(url_for('dashboard'))
    
    clicks = ClickLog.query.filter_by(url_id=url_entry.id).order_by(ClickLog.clicked_at.desc()).all()
    return render_template('url_stats.html', url=url_entry, clicks=clicks)

@app.route('/url/<short_url>/edit', methods=['GET', 'POST'])
@login_required
def edit_url(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first_or_404()
    if url_entry.user_id != current_user.id:
        flash("You don't have permission to edit this URL.", "error")
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        url_entry.title = request.form.get('title')
        url_entry.description = request.form.get('description')
        url_entry.tags = request.form.get('tags')
        url_entry.is_active = bool(request.form.get('is_active'))
        
        if request.form.get('expiry_days'):
            url_entry.expiry_date = datetime.utcnow() + timedelta(days=int(request.form.get('expiry_days')))
        
        db.session.commit()
        flash("URL updated successfully.", "success")
        return redirect(url_for('dashboard'))
    
    return render_template('edit_url.html', url=url_entry)

@app.route('/api/stats/<short_url>')
@login_required
def api_stats(short_url):
    url_entry = URL.query.filter_by(short_url=short_url).first_or_404()
    if url_entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    clicks = ClickLog.query.filter_by(url_id=url_entry.id).all()
    stats = {
        'total_clicks': len(clicks),
        'countries': {},
        'devices': {},
        'browsers': {},
        'referrers': {}
    }
    
    for click in clicks:
        # Count by country
        if click.country:
            stats['countries'][click.country] = stats['countries'].get(click.country, 0) + 1
        
        # Count by device
        if click.device_type:
            stats['devices'][click.device_type] = stats['devices'].get(click.device_type, 0) + 1
        
        # Count by browser
        if click.browser:
            stats['browsers'][click.browser] = stats['browsers'].get(click.browser, 0) + 1
        
        # Count by referrer
        if click.referrer:
            stats['referrers'][click.referrer] = stats['referrers'].get(click.referrer, 0) + 1
    
    return jsonify(stats)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Handle the contact form submission logic here (e.g., send an email)
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        flash('Thank you for reaching out! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
