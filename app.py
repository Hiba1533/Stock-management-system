from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from flask_mysqldb import MySQL
from functools import wraps
from datetime import datetime
import io
import base64
import json
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg')  # Set the backend before importing pyplot
import matplotlib.pyplot as plt
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = '123'  # Change this for production!

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Chimu2323'  # Set your MySQL password
app.config['MYSQL_DB'] = 'stock_management'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Helper Functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login to access this page', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or session.get('role') != 'admin':
            flash('You do not have permission to access this page', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
@login_required
def dashboard():
    try:
        cur = mysql.connection.cursor()

        # Total products
        cur.execute("SELECT COUNT(*) AS total FROM products")
        products = (cur.fetchone() or {}).get('total', 0) or 0

        # Low stock count
        cur.execute("""
            SELECT COUNT(*) AS low_stock
            FROM products p
            JOIN inventory i ON p.product_id = i.product_id
            WHERE i.quantity <= p.min_stock_level
        """)
        low_stock = (cur.fetchone() or {}).get('low_stock', 0) or 0

        # Monthly sales (can be NULL if no rows)
        cur.execute("""
            SELECT SUM(grand_total) AS sales
            FROM sales_orders
            WHERE MONTH(order_date) = MONTH(CURRENT_DATE())
              AND YEAR(order_date) = YEAR(CURRENT_DATE())
              AND status = 'completed'
        """)
        monthly_sales = (cur.fetchone() or {}).get('sales', 0) or 0.0

        # Inventory value (can be NULL if no rows)
        cur.execute("""
            SELECT SUM(i.quantity * p.cost_price) AS inv_value
            FROM inventory i
            JOIN products p ON p.product_id = i.product_id
        """)
        inventory_value = (cur.fetchone() or {}).get('inv_value', 0) or 0.0

        # Recent sales
        cur.execute("""
            SELECT o.order_id, o.order_date, COALESCE(c.name,'Walk-in') AS customer, o.grand_total
            FROM sales_orders o
            LEFT JOIN customers c ON o.customer_id = c.customer_id
            ORDER BY o.order_date DESC
            LIMIT 5
        """)
        recent_sales = cur.fetchall() or []

        # Recent purchases
        cur.execute("""
            SELECT p.po_id, p.order_date, s.name AS supplier, p.total_amount
            FROM purchase_orders p
            JOIN suppliers s ON p.supplier_id = s.supplier_id
            ORDER BY p.order_date DESC
            LIMIT 5
        """)
        recent_purchases = cur.fetchall() or []

        # Example chart data (safe defaults)
        cur.execute("""
            SELECT DATE_FORMAT(order_date, '%Y-%m') AS month, SUM(grand_total) AS total
            FROM sales_orders
            WHERE status='completed'
            GROUP BY DATE_FORMAT(order_date, '%Y-%m')
            ORDER BY month
            LIMIT 12
        """)
        rows = cur.fetchall() or []
        sales_chart_labels = [r['month'] for r in rows]
        sales_chart_values = [float(r['total'] or 0) for r in rows]

        cur.close()

        return render_template(
            'dashboard.html',
            products=products,
            low_stock=low_stock,
            monthly_sales=float(monthly_sales or 0),
            inventory_value=float(inventory_value or 0),
            recent_sales=recent_sales,
            recent_purchases=recent_purchases,
            sales_chart_labels=sales_chart_labels,
            sales_chart_values=sales_chart_values
        )

    except Exception as e:
        # Always pass defaults to avoid UndefinedError
        flash(f'Error loading dashboard: {e}', 'danger')
        return render_template(
            'dashboard.html',
            products=0,
            low_stock=0,
            monthly_sales=0.0,
            inventory_value=0.0,
            recent_sales=[],
            recent_purchases=[],
            sales_chart_labels=[],
            sales_chart_values=[]
        )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hardcoded admin credentials (INSECURE - FOR DEVELOPMENT ONLY)
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            session['user_id'] = 1
            session['username'] = 'admin'
            session['role'] = 'admin'
            session['full_name'] = 'Administrator'
            flash('Login successful', 'success')
            return redirect(url_for('dashboard'))
        
        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()
            
            if user and (
            
                ('password' in user and (user['password'] == password)) or
            
                ('password' in user and isinstance(user['password'], str) and user['password'].startswith(('pbkdf2:', 'scrypt:', 'argon2:')) and check_password_hash(user['password'], password))
            
            ):
            
                session['logged_in'] = True
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['full_name'] = user['full_name']
                flash('Login successful', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password', 'danger')
        
        except Exception as e:
            flash(f'Login error: {str(e)}', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# Products Management
@app.route('/products')
@login_required
def products():
    cur = mysql.connection.cursor()
    
    # Get all products with inventory and category info
    cur.execute("""
        SELECT p.*, c.name as category_name, i.quantity 
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.category_id
        LEFT JOIN inventory i ON p.product_id = i.product_id
    """)
    products = cur.fetchall()
    
    # Get categories for dropdown
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()
    
    cur.close()
    
    return render_template('products.html', products=products, categories=categories)

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    if request.method == 'POST':
        sku = request.form['sku']
        name = request.form['name']
        description = request.form['description']
        category_id = request.form['category_id'] if request.form['category_id'] else None
        brand = request.form['brand']
        size = request.form['size']
        color = request.form['color']
        unit_price = float(request.form['unit_price'])
        cost_price = float(request.form['cost_price'])
        min_stock_level = int(request.form['min_stock_level'])
        
        cur = mysql.connection.cursor()
        
        try:
            # Insert product
            cur.execute("""
                INSERT INTO products (sku, name, description, category_id, brand, size, color, 
                                     unit_price, cost_price, min_stock_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (sku, name, description, category_id, brand, size, color, unit_price, cost_price, min_stock_level))
            
            # Get the inserted product ID
            product_id = cur.lastrowid
            
            # Initialize inventory
            cur.execute("INSERT INTO inventory (product_id, quantity) VALUES (%s, 0)", (product_id,))
            
            mysql.connection.commit()
            flash('Product added successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'create', 'products', product_id, None, json.dumps({
                'sku': sku,
                'name': name,
                'description': description,
                'category_id': category_id,
                'brand': brand,
                'size': size,
                'color': color,
                'unit_price': unit_price,
                'cost_price': cost_price,
                'min_stock_level': min_stock_level
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('products'))

@app.route('/edit_product/<int:product_id>', methods=['POST'])
@login_required
def edit_product(product_id):
    if request.method == 'POST':
        sku = request.form['sku']
        name = request.form['name']
        description = request.form['description']
        category_id = request.form['category_id'] if request.form['category_id'] else None
        brand = request.form['brand']
        size = request.form['size']
        color = request.form['color']
        unit_price = float(request.form['unit_price'])
        cost_price = float(request.form['cost_price'])
        min_stock_level = int(request.form['min_stock_level'])
        
        cur = mysql.connection.cursor()
        
        try:
            # Get old values for audit log
            cur.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
            old_product = cur.fetchone()
            
            # Update product
            cur.execute("""
                UPDATE products 
                SET sku = %s, name = %s, description = %s, category_id = %s, brand = %s, 
                    size = %s, color = %s, unit_price = %s, cost_price = %s, min_stock_level = %s
                WHERE product_id = %s
            """, (sku, name, description, category_id, brand, size, color, 
                 unit_price, cost_price, min_stock_level, product_id))
            
            mysql.connection.commit()
            flash('Product updated successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'update', 'products', product_id, json.dumps(old_product), json.dumps({
                'sku': sku,
                'name': name,
                'description': description,
                'category_id': category_id,
                'brand': brand,
                'size': size,
                'color': color,
                'unit_price': unit_price,
                'cost_price': cost_price,
                'min_stock_level': min_stock_level
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating product: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('products'))

@app.route('/delete_product/<int:product_id>')
@login_required
@admin_required
def delete_product(product_id):
    cur = mysql.connection.cursor()
    
    try:
        # Get product details for audit log
        cur.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
        product = cur.fetchone()
        
        # Delete from inventory first
        cur.execute("DELETE FROM inventory WHERE product_id = %s", (product_id,))
        
        # Then delete the product
        cur.execute("DELETE FROM products WHERE product_id = %s", (product_id,))
        
        mysql.connection.commit()
        flash('Product deleted successfully', 'success')
        
        # Log the action
        log_action(session['user_id'], 'delete', 'products', product_id, json.dumps(product), None)
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting product: {str(e)}', 'danger')
    
    finally:
        cur.close()
    
    return redirect(url_for('products'))

# Inventory Management
@app.route('/inventory')
@login_required
def inventory():
    cur = mysql.connection.cursor()
    
    # Get inventory with product details
    cur.execute("""
        SELECT p.product_id, p.sku, p.name, p.brand, p.min_stock_level, 
               i.quantity, p.unit_price, (i.quantity * p.unit_price) as inventory_value
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id
        ORDER BY p.name
    """)
    inventory = cur.fetchall()
    
    # Get low stock items
    cur.execute("""
        SELECT p.product_id, p.sku, p.name, p.brand, p.min_stock_level, i.quantity
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id
        WHERE i.quantity <= p.min_stock_level
        ORDER BY i.quantity ASC
    """)
    low_stock = cur.fetchall()
    
    cur.close()
    
    return render_template('inventory.html', inventory=inventory, low_stock=low_stock)

@app.route('/adjust_inventory', methods=['POST'])
@login_required
def adjust_inventory():
    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        adjustment = int(request.form['adjustment'])
        notes = request.form['notes']
        
        cur = mysql.connection.cursor()
        
        try:
            # Get current quantity
            cur.execute("SELECT quantity FROM inventory WHERE product_id = %s", (product_id,))
            current_qty = cur.fetchone()['quantity']
            
            new_qty = current_qty + adjustment
            
            if new_qty < 0:
                flash('Cannot adjust inventory to negative quantity', 'danger')
                return redirect(url_for('inventory'))
            
            # Update inventory
            cur.execute("UPDATE inventory SET quantity = %s WHERE product_id = %s", (new_qty, product_id))
            
            # Record stock movement
            movement_type = 'adjustment' if adjustment >= 0 else 'return'
            cur.execute("""
                INSERT INTO stock_movements (product_id, quantity, movement_type, reference_id, notes, created_by)
                VALUES (%s, %s, %s, NULL, %s, %s)
            """, (product_id, abs(adjustment), movement_type, notes, session['user_id']))
            
            mysql.connection.commit()
            flash('Inventory adjusted successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'update', 'inventory', product_id, 
                     f'Quantity: {current_qty}', f'Quantity: {new_qty}')
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adjusting inventory: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('inventory'))

# Sales Management
from io import BytesIO
# from fpdf import FPDF  # make sure this import exists at the top

@app.route('/sales/<int:order_id>/invoice')
@login_required
def generate_invoice(order_id):
    cur = mysql.connection.cursor()

    # Order header
    cur.execute("""
        SELECT o.order_id, o.order_date, o.customer_id, o.total_amount, o.discount, o.tax, o.grand_total,
               COALESCE(c.name, 'Walk-in') AS customer_name
        FROM sales_orders o
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        WHERE o.order_id = %s
    """, (order_id,))
    order = cur.fetchone()

    # Order lines
    cur.execute("""
        SELECT oi.quantity, oi.unit_price, oi.total_price, p.name, p.sku
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cur.fetchall()
    cur.close()

    if not order:
        flash('Order not found', 'warning')
        return redirect(url_for('sales'))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(True, 15)
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, f"INVOICE #{order['order_id']}", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Date: {order['order_date']}", ln=True)
    pdf.cell(0, 6, f"Customer: {order['customer_name']}", ln=True)
    pdf.ln(6)

    # Table header
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(100, 8, "Product", border=1)
    pdf.cell(20, 8, "Qty", border=1, align="R")
    pdf.cell(30, 8, "Price", border=1, align="R")
    pdf.cell(40, 8, "Total", border=1, ln=True, align="R")

    # Table rows
    pdf.set_font("Helvetica", size=11)
    for it in items:
        name = f"{it['name']} ({it['sku']})"
        pdf.cell(100, 8, name, border=1)
        pdf.cell(20, 8, f"{it['quantity']}", border=1, align="R")
        pdf.cell(30, 8, f"${it['unit_price']:.2f}", border=1, align="R")
        pdf.cell(40, 8, f"${it['total_price']:.2f}", border=1, ln=True, align="R")

    pdf.ln(4)
    pdf.cell(150, 8, "Subtotal:", align="R")
    pdf.cell(40, 8, f"${order['total_amount']:.2f}", ln=True, align="R")
    pdf.cell(150, 8, "Discount:", align="R")
    pdf.cell(40, 8, f"${order['discount']:.2f}", ln=True, align="R")
    pdf.cell(150, 8, "Tax:", align="R")
    pdf.cell(40, 8, f"${order['tax']:.2f}", ln=True, align="R")
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(150, 10, "Grand Total:", align="R")
    pdf.cell(40, 10, f"${order['grand_total']:.2f}", ln=True, align="R")

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return send_file(buf,
                     as_attachment=True,
                     download_name=f"invoice_{order_id}.pdf",
                     mimetype="application/pdf")


@app.route('/sales')
@login_required
def sales():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT o.order_id, o.order_date,
               COALESCE(c.name, 'Walk-in') AS customer_name,
               o.status, o.total_amount, o.discount, o.tax, o.grand_total,
               u.full_name AS created_by
        FROM sales_orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        JOIN users u ON o.created_by = u.user_id
        ORDER BY o.order_date DESC
    """)
    orders = cur.fetchall()
    cur.close()
    return render_template('sales.html', orders=orders)


@app.route('/create_sale', methods=['GET', 'POST'])
@login_required
def create_sale():
    if request.method == 'GET':
        cur = mysql.connection.cursor()

        # Customers for dropdown
        cur.execute("SELECT * FROM customers ORDER BY name")
        customers = cur.fetchall()

        # Products for selection (show even if inventory missing or zero)
        cur.execute("""
            SELECT 
                p.product_id,
                p.sku,
                p.name,
                COALESCE(p.unit_price, p.cost_price, 0) AS unit_price,
                COALESCE(i.quantity, 0) AS quantity
            FROM products p
            LEFT JOIN inventory i ON i.product_id = p.product_id
            ORDER BY p.name
        """)
        products = cur.fetchall()
        cur.close()

        # NOTE: template name is singular
        return render_template('create_sales.html', customers=customers, products=products)

    # POST
    try:
        items = json.loads(request.form.get('items', '[]'))
        discount = float(request.form.get('discount', 0) or 0)
        tax = float(request.form.get('tax', 0) or 0)
        notes = request.form.get('notes', '')
        customer_id = request.form.get('customer_id') or None

        if not items:
            flash('Please add at least one item', 'warning')
            return redirect(url_for('create_sale'))

        cur = mysql.connection.cursor()

        # Calculate totals
        subtotal = sum(float(item['price']) * int(item['quantity']) for item in items)
        grand_total = subtotal - discount + tax

        # Create sales order
        cur.execute("""
            INSERT INTO sales_orders (customer_id, status, total_amount, discount, tax, grand_total, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (customer_id, 'completed', subtotal, discount, tax, grand_total, notes, session['user_id']))
        order_id = cur.lastrowid

        # Add order items + update inventory + stock movement
        for item in items:
            product_id = int(item['id'])
            quantity = int(item['quantity'])
            price = float(item['price'])

            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, product_id, quantity, price, price * quantity))

            cur.execute("""
                UPDATE inventory SET quantity = quantity - %s WHERE product_id = %s
            """, (quantity, product_id))

            cur.execute("""
                INSERT INTO stock_movements (product_id, quantity, movement_type, reference_id, notes, created_by)
                VALUES (%s, %s, 'sale', %s, %s, %s)
            """, (product_id, quantity, order_id, f'Sale order #{order_id}', session['user_id']))

        mysql.connection.commit()
        cur.close()

        # Log action (after commit)
        log_action(session['user_id'], 'create', 'sales_orders', order_id, None, json.dumps({
            'customer_id': customer_id,
            'status': 'completed',
            'total_amount': subtotal,
            'discount': discount,
            'tax': tax,
            'grand_total': grand_total,
            'notes': notes,
            'items': items
        }))

        flash('Sale completed successfully.', 'success')
        return redirect(url_for('sales'))

    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error creating sale: {e}', 'danger')
        return redirect(url_for('sale_detail', order_id=order_id))


@app.route('/view_sale/<int:order_id>')
@login_required
def view_sale(order_id):
    cur = mysql.connection.cursor()
    
    # Get order details
    cur.execute("""
        SELECT o.*, c.name as customer_name, c.email as customer_email, 
               c.phone as customer_phone, u.full_name as created_by
        FROM sales_orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        JOIN users u ON o.created_by = u.user_id
        WHERE o.order_id = %s
    """, (order_id,))
    order = cur.fetchone()
    
    # Get order items
    cur.execute("""
        SELECT i.*, p.name as product_name, p.sku
        FROM order_items i
        JOIN products p ON i.product_id = p.product_id
        WHERE i.order_id = %s
    """, (order_id,))
    items = cur.fetchall()
    
    cur.close()
    
    return render_template('view_sales.html', order=order, items=items)

@app.route('/generate_invoice/<int:order_id>')
@login_required
def generate_invoice_new(order_id):
    cur = mysql.connection.cursor()
    
    # Get order details
    cur.execute("""
        SELECT o.*, c.name as customer_name, c.email as customer_email, 
               c.phone as customer_phone, c.address as customer_address,
               u.full_name as created_by
        FROM sales_orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        JOIN users u ON o.created_by = u.user_id
        WHERE o.order_id = %s
    """, (order_id,))
    order = cur.fetchone()
    
    # Get order items
    cur.execute("""
        SELECT i.*, p.name as product_name, p.sku
        FROM order_items i
        JOIN products p ON i.product_id = p.product_id
        WHERE i.order_id = %s
    """, (order_id,))
    items = cur.fetchall()
    
    cur.close()
    
    # Generate PDF invoice
    pdf = FPDF()
    pdf.add_page()
    
    # Add logo and header
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'INVOICE', 0, 1, 'C')
    pdf.ln(10)
    
    # Company info
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, 'Stock Management System', 0, 1)
    pdf.cell(0, 10, '123 Business Street', 0, 1)
    pdf.cell(0, 10, 'City, State 10001', 0, 1)
    pdf.cell(0, 10, 'Phone: (123) 456-7890', 0, 1)
    pdf.ln(10)
    
    # Invoice details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(40, 10, 'Invoice #:', 0, 0)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, str(order_id), 0, 1)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(40, 10, 'Date:', 0, 0)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, order['order_date'].strftime('%Y-%m-%d'), 0, 1)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(40, 10, 'Customer:', 0, 0)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, order['customer_name'] if order['customer_name'] else 'Walk-in Customer', 0, 1)
    pdf.ln(10)
    
    # Items table
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(20, 10, 'Qty', 1, 0, 'C')
    pdf.cell(100, 10, 'Description', 1, 0)
    pdf.cell(30, 10, 'Unit Price', 1, 0, 'R')
    pdf.cell(30, 10, 'Total', 1, 1, 'R')
    
    pdf.set_font('Arial', '', 12)
    for item in items:
        pdf.cell(20, 10, str(item['quantity']), 1, 0, 'C')
        pdf.cell(100, 10, f"{item['product_name']} ({item['sku']})", 1, 0)
        pdf.cell(30, 10, f"${item['unit_price']:.2f}", 1, 0, 'R')
        pdf.cell(30, 10, f"${item['total_price']:.2f}", 1, 1, 'R')
    
    # Totals
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(150, 10, 'Subtotal:', 0, 0, 'R')
    pdf.set_font('Arial', '', 12)
    pdf.cell(30, 10, f"${order['total_amount']:.2f}", 0, 1, 'R')
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(150, 10, 'Discount:', 0, 0, 'R')
    pdf.set_font('Arial', '', 12)
    pdf.cell(30, 10, f"-${order['discount']:.2f}", 0, 1, 'R')
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(150, 10, 'Tax:', 0, 0, 'R')
    pdf.set_font('Arial', '', 12)
    pdf.cell(30, 10, f"${order['tax']:.2f}", 0, 1, 'R')
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(150, 10, 'Grand Total:', 0, 0, 'R')
    pdf.set_font('Arial', '', 12)
    pdf.cell(30, 10, f"${order['grand_total']:.2f}", 0, 1, 'R')
    
    # Notes
    if order['notes']:
        pdf.ln(10)
        pdf.set_font('Arial', 'I', 10)
        pdf.multi_cell(0, 10, f"Notes: {order['notes']}")
    
    # Footer
    pdf.set_y(-30)
    pdf.set_font('Arial', 'I', 8)
    pdf.cell(0, 10, 'Thank you for your business!', 0, 0, 'C')
    
    
    result = pdf.output(dest='S')               
    pdf_bytes = bytes(result) if isinstance(result, (bytes, bytearray)) else result.encode('latin1')

    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)

    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'invoice_{order_id}.pdf',
        mimetype='application/pdf'
    )

# Purchase Management
@app.route('/purchases')
@login_required
def purchases():
    cur = mysql.connection.cursor()
    
    # Get purchase orders with supplier info
    cur.execute("""
        SELECT p.po_id, p.order_date, s.name as supplier_name, p.status, 
               p.total_amount, p.expected_delivery, u.full_name as created_by
        FROM purchase_orders p
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        JOIN users u ON p.created_by = u.user_id
        ORDER BY p.order_date DESC
    """)
    orders = cur.fetchall()
    
    cur.close()
    
    return render_template('purchases.html', orders=orders)

@app.route('/create_purchase', methods=['GET', 'POST'])
@login_required
def create_purchase():
    if request.method == 'GET':
        cur = mysql.connection.cursor()
        
        # Get suppliers for dropdown
        cur.execute("SELECT * FROM suppliers ORDER BY name")
        suppliers = cur.fetchall()
        
        # Get products for selection
        cur.execute("""
            SELECT p.product_id, p.sku, p.name, p.cost_price 
            FROM products p
            ORDER BY p.name
        """)
        products = cur.fetchall()
        
        cur.close()
        
        return render_template('create_purchase.html', suppliers=suppliers, products=products)
    
    elif request.method == 'POST':
        supplier_id = int(request.form['supplier_id'])
        expected_delivery = request.form['expected_delivery']
        items = json.loads(request.form['items'])
        notes = request.form['notes']
        
        cur = mysql.connection.cursor()
        
        try:
            # Calculate total
            total = sum(item['price'] * item['quantity'] for item in items)
            
            # Create purchase order
            cur.execute("""
                INSERT INTO purchase_orders (supplier_id, expected_delivery, status, total_amount, notes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (supplier_id, expected_delivery, 'pending', total, notes, session['user_id']))
            
            po_id = cur.lastrowid
            
            # Add PO items
            for item in items:
                product_id = item['id']
                quantity = item['quantity']
                price = item['price']
                
                cur.execute("""
                    INSERT INTO po_items (po_id, product_id, quantity, unit_price, total_price)
                    VALUES (%s, %s, %s, %s, %s)
                """, (po_id, product_id, quantity, price, price * quantity))
            
            mysql.connection.commit()
            flash('Purchase order created successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'create', 'purchase_orders', po_id, None, json.dumps({
                'supplier_id': supplier_id,
                'expected_delivery': expected_delivery,
                'status': 'pending',
                'total_amount': total,
                'notes': notes,
                'items': items
            }))
            
            return jsonify({'success': True, 'po_id': po_id})
            
        except Exception as e:
            mysql.connection.rollback()
            return jsonify({'success': False, 'error': str(e)})
        
        finally:
            cur.close()

@app.route('/receive_purchase/<int:po_id>', methods=['POST'])
@login_required
def receive_purchase(po_id):
    cur = mysql.connection.cursor()
    
    try:
        # Update PO status
        cur.execute("""
            UPDATE purchase_orders 
            SET status = 'received'
            WHERE po_id = %s
        """, (po_id,))
        
        # Get PO items
        cur.execute("SELECT * FROM po_items WHERE po_id = %s", (po_id,))
        items = cur.fetchall()
        
        # Update inventory for each item
        for item in items:
            cur.execute("""
                UPDATE inventory 
                SET quantity = quantity + %s 
                WHERE product_id = %s
            """, (item['quantity'], item['product_id']))
            
            # Record stock movement
            cur.execute("""
                INSERT INTO stock_movements (product_id, quantity, movement_type, reference_id, notes, created_by)
                VALUES (%s, %s, 'purchase', %s, %s, %s)
            """, (item['product_id'], item['quantity'], po_id, f'Purchase order #{po_id}', session['user_id']))
        
        mysql.connection.commit()
        flash('Purchase order marked as received and inventory updated', 'success')
        
        # Log the action
        log_action(session['user_id'], 'update', 'purchase_orders', po_id, 'status: pending', 'status: received')
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error receiving purchase order: {str(e)}', 'danger')
    
    finally:
        cur.close()
    
    return redirect(url_for('purchases'))

# Customer Management
@app.route('/customers')
@login_required
def customers():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM customers ORDER BY name")
    customers = cur.fetchall()
    cur.close()
    return render_template('customers.html', customers=customers)

@app.route('/add_customer', methods=['POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        
        cur = mysql.connection.cursor()
        
        try:
            cur.execute("""
                INSERT INTO customers (name, email, phone, address)
                VALUES (%s, %s, %s, %s)
            """, (name, email, phone, address))
            
            mysql.connection.commit()
            flash('Customer added successfully', 'success')
            
            # Log the action
            customer_id = cur.lastrowid
            log_action(session['user_id'], 'create', 'customers', customer_id, None, json.dumps({
                'name': name,
                'email': email,
                'phone': phone,
                'address': address
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding customer: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('customers'))

@app.route('/edit_customer/<int:customer_id>', methods=['POST'])
@login_required
def edit_customer(customer_id):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        
        cur = mysql.connection.cursor()
        
        try:
            # Get old values for audit log
            cur.execute("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
            old_customer = cur.fetchone()
            
            cur.execute("""
                UPDATE customers 
                SET name = %s, email = %s, phone = %s, address = %s
                WHERE customer_id = %s
            """, (name, email, phone, address, customer_id))
            
            mysql.connection.commit()
            flash('Customer updated successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'update', 'customers', customer_id, json.dumps(old_customer), json.dumps({
                'name': name,
                'email': email,
                'phone': phone,
                'address': address
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating customer: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('customers'))

@app.route('/delete_customer/<int:customer_id>')
@login_required
@admin_required
def delete_customer(customer_id):
    cur = mysql.connection.cursor()
    
    try:
        # Get customer details for audit log
        cur.execute("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
        customer = cur.fetchone()
        
        cur.execute("DELETE FROM customers WHERE customer_id = %s", (customer_id,))
        
        mysql.connection.commit()
        flash('Customer deleted successfully', 'success')
        
        # Log the action
        log_action(session['user_id'], 'delete', 'customers', customer_id, json.dumps(customer), None)
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting customer: {str(e)}', 'danger')
    
    finally:
        cur.close()
    
    return redirect(url_for('customers'))

# Supplier Management
@app.route('/suppliers')
@login_required
def suppliers():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM suppliers ORDER BY name")
    suppliers = cur.fetchall()
    cur.close()
    return render_template('suppliers.html', suppliers=suppliers)

@app.route('/add_supplier', methods=['POST'])
@login_required
def add_supplier():
    if request.method == 'POST':
        name = request.form['name']
        contact_person = request.form['contact_person']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        
        cur = mysql.connection.cursor()
        
        try:
            cur.execute("""
                INSERT INTO suppliers (name, contact_person, email, phone, address)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, contact_person, email, phone, address))
            
            mysql.connection.commit()
            flash('Supplier added successfully', 'success')
            
            # Log the action
            supplier_id = cur.lastrowid
            log_action(session['user_id'], 'create', 'suppliers', supplier_id, None, json.dumps({
                'name': name,
                'contact_person': contact_person,
                'email': email,
                'phone': phone,
                'address': address
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding supplier: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('suppliers'))

@app.route('/edit_supplier/<int:supplier_id>', methods=['POST'])
@login_required
def edit_supplier(supplier_id):
    if request.method == 'POST':
        name = request.form['name']
        contact_person = request.form['contact_person']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        
        cur = mysql.connection.cursor()
        
        try:
            # Get old values for audit log
            cur.execute("SELECT * FROM suppliers WHERE supplier_id = %s", (supplier_id,))
            old_supplier = cur.fetchone()
            
            cur.execute("""
                UPDATE suppliers 
                SET name = %s, contact_person = %s, email = %s, phone = %s, address = %s
                WHERE supplier_id = %s
            """, (name, contact_person, email, phone, address, supplier_id))
            
            mysql.connection.commit()
            flash('Supplier updated successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'update', 'suppliers', supplier_id, json.dumps(old_supplier), json.dumps({
                'name': name,
                'contact_person': contact_person,
                'email': email,
                'phone': phone,
                'address': address
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating supplier: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('suppliers'))

@app.route('/delete_supplier/<int:supplier_id>')
@login_required
@admin_required
def delete_supplier(supplier_id):
    cur = mysql.connection.cursor()
    
    try:
        # Get supplier details for audit log
        cur.execute("SELECT * FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        supplier = cur.fetchone()
        
        cur.execute("DELETE FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        
        mysql.connection.commit()
        flash('Supplier deleted successfully', 'success')
        
        # Log the action
        log_action(session['user_id'], 'delete', 'suppliers', supplier_id, json.dumps(supplier), None)
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting supplier: {str(e)}', 'danger')
    
    finally:
        cur.close()
    
    return redirect(url_for('suppliers'))

# User Management
@app.route('/users')
@login_required
@admin_required
def users():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users ORDER BY role, username")
    users = cur.fetchall()
    cur.close()
    return render_template('users.html', users=users)

from werkzeug.security import generate_password_hash

from werkzeug.security import generate_password_hash

@app.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        
        # Hash the password only once using bcrypt
        password = request.form['password']
        hashed_password = generate_password_hash(password)  # default pbkdf2:sha256
        # or explicit:
        # hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

        full_name = request.form['full_name']
        email = request.form['email']
        role = request.form['role']

        cur = mysql.connection.cursor()
        
        try:
            # Insert the user into the database with the hashed password
            cur.execute("""
                INSERT INTO users (username, password, full_name, email, role)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, hashed_password, full_name, email, role))
            
            mysql.connection.commit()
            flash('User added successfully', 'success')
            
            # Log the action
            user_id = cur.lastrowid
            log_action(session['user_id'], 'create', 'users', user_id, None, json.dumps({
                'username': username,
                'full_name': full_name,
                'email': email,
                'role': role
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding user: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('users'))


@app.route('/edit_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    if request.method == 'POST':
        username = request.form['username']
        full_name = request.form['full_name']
        email = request.form['email']
        role = request.form['role']
        
        cur = mysql.connection.cursor()
        
        try:
            # Get old values for audit log
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            old_user = cur.fetchone()
            
            # Check if password is being updated
            if request.form['password']:
                password = generate_password_hash(request.form['password'])
                cur.execute("""
                    UPDATE users 
                    SET username = %s, password = %s, full_name = %s, email = %s, role = %s
                    WHERE user_id = %s
                """, (username, password, full_name, email, role, user_id))
            else:
                cur.execute("""
                    UPDATE users 
                    SET username = %s, full_name = %s, email = %s, role = %s
                    WHERE user_id = %s
                """, (username, full_name, email, role, user_id))
            
            mysql.connection.commit()
            flash('User updated successfully', 'success')
            
            # Log the action
            log_action(session['user_id'], 'update', 'users', user_id, json.dumps(old_user), json.dumps({
                'username': username,
                'full_name': full_name,
                'email': email,
                'role': role
            }))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')
        
        finally:
            cur.close()
        
        return redirect(url_for('users'))

@app.route('/delete_user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    # Prevent deleting own account
    if user_id == session['user_id']:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('users'))
    
    cur = mysql.connection.cursor()
    
    try:
        # Get user details for audit log
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        mysql.connection.commit()
        flash('User deleted successfully', 'success')
        
        # Log the action
        log_action(session['user_id'], 'delete', 'users', user_id, json.dumps(user), None)
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    finally:
        cur.close()
    
    return redirect(url_for('users'))

# Reports
@app.route('/reports')
@login_required
def reports():
    cur = mysql.connection.cursor()
    
    # Sales report data
    cur.execute("""
        SELECT DATE_FORMAT(order_date, '%Y-%m') as month, 
               COUNT(*) as orders, 
               SUM(grand_total) as revenue
        FROM sales_orders
        WHERE status = 'completed'
        GROUP BY DATE_FORMAT(order_date, '%Y-%m')
        ORDER BY month DESC
        LIMIT 12
    """)
    sales_report = cur.fetchall()
    
    # Inventory valuation
    cur.execute("""
        SELECT p.name, i.quantity, p.unit_price, (i.quantity * p.unit_price) as value
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id
        ORDER BY value DESC
    """)
    inventory_value = cur.fetchall()
    
    # Total inventory value
    cur.execute("""
        SELECT SUM(i.quantity * p.unit_price) as total_value
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id
    """)
    total_inventory_value = cur.fetchone()['total_value'] or 0
    
    # Top customers
    cur.execute("""
        SELECT c.name, COUNT(o.order_id) as orders, SUM(o.grand_total) as total_spent
        FROM sales_orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.status = 'completed'
        GROUP BY c.name
        ORDER BY total_spent DESC
        LIMIT 5
    """)
    top_customers = cur.fetchall()
    
    cur.close()
    
    return render_template('reports.html', 
                         sales_report=sales_report,
                         inventory_value=inventory_value,
                         total_inventory_value=total_inventory_value,
                         top_customers=top_customers)

# Helper function for audit logging
def log_action(user_id, action, table_name, record_id, old_value, new_value):
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            INSERT INTO audit_log (user_id, action, table_affected, record_id, old_value, new_value)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, action, table_name, record_id, old_value, new_value))
        mysql.connection.commit()
    except Exception as e:
        mysql.connection.rollback()
        print(f"Error logging action: {str(e)}")
    finally:
        cur.close()
def create_admin_user():
    try:
        cur = mysql.connection.cursor()
        # Check if admin exists
        cur.execute("SELECT * FROM users WHERE username = 'admin'")
        admin = cur.fetchone()
        
        if not admin:
            cur.execute("""
                INSERT INTO users (username, password, full_name, email, role)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                'admin',
                'admin123',  # Storing plaintext password (INSECURE)
                'Administrator',
                'admin@example.com',
                'admin'
            ))
            mysql.connection.commit()
            print("Admin user created successfully")
        cur.close()
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")

# Create admin user when starting app
with app.app_context():
    create_admin_user()

if __name__ == '__main__':
    app.run(debug=True)