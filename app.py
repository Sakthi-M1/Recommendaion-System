from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pymongo import MongoClient
import pandas as pd
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import random
import certifi
import smtplib
from email.mime.text import MIMEText
import os

app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Change this to a secure secret key

# Email configuration (from your environment variables)
EMAIL_USER = os.environ.get('EMAIL_USER', 'plantbasedgrazing.co@gmail.com')
EMAIL_PASS = os.environ.get('EMAIL_PASS', 'hrrbbslcvspskvbd')

# MongoDB Connection for Products
try:
    client = MongoClient(
        'mongodb+srv://sakthidj008:lTk7r3zpPdfoYrHV@cluster0.3yvq4c8.mongodb.net/?retryWrites=true&w=majority',
        tls=True,
        tlsCAFile=certifi.where()
    )

    db_products = client['product_db']
    collection_products = db_products['products']

    db_users = client['user_db']
    collection_users = db_users['users']

    # Test the connection
    client.server_info()
    print("Connected to MongoDB successfully!")

except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    client = None
    db_products = None
    collection_products = None
    db_users = None
    collection_users = None

# Flag to check if databases are initialized
products_initialized = False
users_initialized = False

# Initialize Product Database
def initialize_product_database(data):
    global products_initialized
    if not products_initialized and db_products is not None:
        try:
            for index, row in data.iterrows():
                product_name = row.get('Product Name', 'Unknown')
                brand = row.get('Brand', 'Unknown')
                product = {
                    'customer_id': str(row.get('Customer ID', str(index))),
                    'age': int(row.get('Age', 0)) if pd.notna(row.get('Age')) else None,
                    'gender': row.get('Gender') if pd.notna(row.get('Gender')) else None,
                    'category': row.get('Category', 'Unknown'),
                    'brand': brand,
                    'prices': {
                        'amazon': float(row.get('Price on Amazon', 0.0)) if pd.notna(row.get('Price on Amazon')) else 0.0,
                        'flipkart': float(row.get('Price on Flipkart', 0.0)) if pd.notna(row.get('Price on Flipkart')) else 0.0,
                        'reliance_digital': float(row.get('Price on Reliance Digital', 0.0)) if pd.notna(row.get('Price on Reliance Digital')) else 0.0
                    },
                    'lowest_platform': row.get('Lowest Price Website', 'flipkart'),
                    'links': {
                        'amazon': f"https://www.amazon.in/s?k={brand}+{product_name}",
                        'flipkart': f"https://www.flipkart.com/search?q={brand}+{product_name}",
                        'reliance_digital': f"https://www.reliancedigital.in/search?q={brand}+{product_name}"
                    },
                    'image': f"https://via.placeholder.com/200?text={brand}+{product_name}",
                    'stock_sold': random.randint(50, 500),
                    'timestamp': datetime.utcnow()
                }
                collection_products.update_one({'customer_id': str(product['customer_id'])}, {'$set': product}, upsert=True)
            products_initialized = True
            print("Product database initialized successfully!")
        except KeyError as ke:
            flash(f"Missing column in Excel: {ke}", 'warning')
            print(f"Error initializing product database: Missing column {ke}")
        except Exception as e:
            flash(f'Error initializing product database: {e}', 'warning')
            print(f"Error initializing product database: {e}")

# Initialize on first request
@app.before_request
def initialize_databases():
    global products_initialized, users_initialized
    if not products_initialized and db_products is not None:
        try:
            df = pd.read_excel('Product_Pricing_Comparison.xlsx')
            initialize_product_database(df)
        except FileNotFoundError:
            flash('Excel file not found. Please upload the Product_Pricing_Comparison.xlsx file.', 'warning')
        except Exception as e:
            flash(f'Error initializing product database: {e}', 'warning')
    if not users_initialized and db_users is not None:
        users_initialized = True

# Default Route
@app.route('/')
def index():
    return redirect(url_for('login'))

# Handle favicon request to suppress 404
@app.route('/favicon.ico')
def favicon():
    return '', 204

# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        shop_name = request.form['shop_name']
        email = request.form['email']
        location = request.form['location']
        password = request.form['password']

        if db_users is None:
            flash('Database connection failed. Please try again later.', 'warning')
            return redirect(url_for('register'))

        if collection_users.find_one({'email': email}):
            flash('Email already registered.', 'warning')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        user = {
            'shop_name': shop_name,
            'email': email,
            'location': location,
            'password': hashed_password,
            'search_history': []
        }
        collection_users.insert_one(user)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if db_users is None:
            flash('Database connection failed. Please try again later.', 'warning')
            return redirect(url_for('login'))

        user = collection_users.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['email'] = email
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'warning')
            print(f"Login attempt failed for email: {email}")

    return render_template('login.html')

# Dashboard Route (Protected)
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'email' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    products = []
    sales_labels = []
    sales_values = []
    query = ''
    price_analysis = {}
    stock_stats = {}

    if db_products is None:
        flash('Database connection failed. Please check your MongoDB connection.', 'warning')
        return render_template('dashboard.html', products=products, query=query, sales_labels=sales_labels, sales_values=sales_values, price_analysis={}, stock_stats={})

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'search':
            min_age = request.form.get('min_age')
            max_age = request.form.get('max_age')
            gender = request.form.get('gender')
            query = request.form.get('query', '')
            product_name = request.form.get('product_name', '')
            min_price = request.form.get('min_price')
            max_price = request.form.get('max_price')

            mongo_query = {}
            # Replace single age with age range
            if min_age and max_age:
                mongo_query['age'] = {'$gte': int(min_age), '$lte': int(max_age)}
            elif min_age:
                mongo_query['age'] = {'$gte': int(min_age)}
            elif max_age:
                mongo_query['age'] = {'$lte': int(max_age)}

            if gender:
                mongo_query['gender'] = gender
            if query:
                if query in ['Supermarket', 'Electronic']:
                    mongo_query['category'] = {'$regex': query, '$options': 'i'}
                else:
                    mongo_query['$or'] = [
                        {'category': {'$regex': query, '$options': 'i'}},
                        {'brand': {'$regex': query, '$options': 'i'}}
                    ]
            if product_name:
                mongo_query['brand'] = {'$regex': product_name, '$options': 'i'}
            if min_price and max_price:
                mongo_query['$expr'] = {
                    '$and': [
                        {'$lte': [{'$min': ['$prices.amazon', '$prices.flipkart', '$prices.reliance_digital']}, float(max_price)]},
                        {'$gte': [{'$min': ['$prices.amazon', '$prices.flipkart', '$prices.reliance_digital']}, float(min_price)]}
                    ]
                }
            elif min_price:
                mongo_query['$expr'] = {'$gte': [{'$min': ['$prices.amazon', '$prices.flipkart', '$prices.reliance_digital']}, float(min_price)]}
            elif max_price:
                mongo_query['$expr'] = {'$lte': [{'$min': ['$prices.amazon', '$prices.flipkart', '$prices.reliance_digital']}, float(max_price)]}

            products = list(collection_products.find(mongo_query).limit(10))

            # Store search history for the current user
            user_email = session['email']
            search_history = {
                'user_email': user_email,
                'search_query': product_name or query,
                'min_age': min_age,
                'max_age': max_age,
                'timestamp': datetime.utcnow()
            }
            collection_users.update_one({'email': user_email}, {'$push': {'search_history': search_history}})

        elif action == 'add_product':
            product_name = request.form.get('new_product_name')
            brand = request.form.get('new_brand')
            category = request.form.get('new_category')
            price_amazon = float(request.form.get('new_price_amazon', 0.0))
            price_flipkart = float(request.form.get('new_price_flipkart', 0.0))
            price_reliance = float(request.form.get('new_price_reliance', 0.0))

            # Determine lowest price platform
            prices = {
                'amazon': price_amazon,
                'flipkart': price_flipkart,
                'reliance_digital': price_reliance
            }
            lowest_platform = min(prices, key=prices.get)

            new_product = {
                'customer_id': str(random.randint(1000, 9999)),
                'age': None,
                'gender': None,
                'category': category,
                'brand': brand,
                'prices': prices,
                'lowest_platform': lowest_platform,
                'links': {
                    'amazon': f"https://www.amazon.in/s?k={brand}+{product_name}",
                    'flipkart': f"https://www.flipkart.com/search?q={brand}+{product_name}",
                    'reliance_digital': f"https://www.reliancedigital.in/search?q={brand}+{product_name}"
                },
                'image': f"https://via.placeholder.com/200?text={brand}+{product_name}",
                'stock_sold': 0,
                'timestamp': datetime.utcnow()
            }

            # Insert new product
            collection_products.insert_one(new_product)

            # Find users who searched for this product and send emails
            search_history = collection_users.find({'search_history.search_query': {'$regex': product_name, '$options': 'i'}})
            for user in search_history:
                send_notification_email(user['email'], product_name, prices[lowest_platform])

            flash('Product added successfully and notifications sent!', 'success')
            return redirect(url_for('dashboard'))

        # Price Analysis
        for product in products:
            prices = product['prices']
            min_price = min(prices.values())
            max_price = max(prices.values())
            price_analysis[product['customer_id']] = {
                'min_price': min_price,
                'max_price': max_price,
                'difference': max_price - min_price,
                'percentage_diff': ((max_price - min_price) / min_price * 100) if min_price > 0 else 0
            }

        # Stock Statistics
        for product in products:
            category = product['category']
            stock_sold = product.get('stock_sold', 0)
            if category in stock_stats:
                stock_stats[category] += stock_sold
            else:
                stock_stats[category] = stock_sold

        sales_labels = list(stock_stats.keys())
        sales_values = list(stock_stats.values())

    return render_template('dashboard.html', products=products, query=query, sales_labels=sales_labels, sales_values=sales_values, price_analysis=price_analysis, stock_stats=stock_stats)

# Logout Route
@app.route('/logout')
def logout():
    session.pop('email', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# New function to send email
def send_notification_email(to_email, product_name, price):
    msg = MIMEText(f"Dear Customer,\n\nGreat news! The product you previously searched for, {product_name}, has been added to our platform. It's now available at a price of {price} INR.\n\nBest regards,\nYour E-commerce Team")
    msg['Subject'] = f'Your Searched Product {product_name} is Now Available!'
    msg['From'] = EMAIL_USER
    msg['To'] = to_email

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

if __name__ == '__main__':
    app.run(debug=True)