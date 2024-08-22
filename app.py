import os
from flask import Flask, jsonify, request #imports flask and allows us to instantiate an app
from flask_sqlalchemy import SQLAlchemy # this is Object Relational Mapper
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session # this is a class that all of our classes will inherit
# provides base functionality for converting python objects to rows of data
from sqlalchemy import select, delete #query our database with a select statement
from flask_marshmallow import Marshmallow # creates our schema to validate incoming and outgoing data
from flask_cors import CORS # Cross Origin Resource Sharing - allows our application to be accessed by 3rd parties
import datetime
import jwt
from typing import List #tie a one to many relationship back to the one
from marshmallow import ValidationError, fields, validate, Schema
from werkzeug.security import generate_password_hash, check_password_hash





app = Flask(__name__)
CORS(app) #initializes CORS for our application
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv('DATABASE_URL')
#app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://root:Dolphin25!@localhost/e_commerce_db2"
#  'mysql+mysqlconnector://root:your_password@localhost/e_commerce_db'
#                           user  password                database name

# create a Base class for all of our Models (classes that become tables) to inherit from
# the child classes can then create attributes that become columns inside of tables in our db
# objects from those tables create rows of data in our db
class Base(DeclarativeBase):
    pass

# instantiate our db
db = SQLAlchemy(app, model_class=Base) #tells the db instance that we use the Base class for the model functionality
# model - class that becomes a table in the db
ma = Marshmallow(app) # creating a marshmallow object for the schema creation



# ========================= DB MODELS ==============================
class Customer(Base): #importing the Base class gives this class model functionality
    __tablename__ = "Customers" # sets the name of the table in our database
    # type hinting - column name is an attribute and we're creating a ty
    # variable_name: type <-- type hinting, what is the expected type for this variable    
    customer_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    email: Mapped[str] = mapped_column(db.String(320), nullable=False)
    phone: Mapped[str] = mapped_column(db.String(15))
    # one-to-one relationship with customer account
    customer_account: Mapped["CustomerAccount"] = db.relationship(back_populates="customer")
    # create a one-to-many relationship with Order
    orders: Mapped[List["Order"]] = db.relationship(back_populates="customer")

# Customer Account with a one to one relationship with the Customer table
class CustomerAccount(Base):
    __tablename__ = "Customer_Accounts"
    # attribute_name: attribute type = any constraints for that column
    account_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(db.String(255), nullable = False)
    # create the foreign key from the customer table
    customer_id: Mapped[int] = mapped_column(db.ForeignKey('Customers.customer_id'))
    # create the back reference relationship between objects of the classes
    customer: Mapped["Customer"] = db.relationship(back_populates="customer_account")
     
    def set_password(self, password: str):
        self.password = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password, password)
    
# associate table between orders and products to manage the many to many relationship
order_product = db.Table(
    "Order_Product", #association table name
    Base.metadata,
    db.Column("order_id", db.ForeignKey("Orders.order_id"), primary_key=True),
    db.Column("product_id", db.ForeignKey("Products.product_id"), primary_key=True)      
)

# creating Orders and a one to many relationship bewtween Customer and Order
class Order(Base):
    __tablename__ = "Orders"

    order_id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(db.Date, nullable = False)
    # creating relationship with Customer 
    customer_id: Mapped[int] = mapped_column(db.ForeignKey("Customers.customer_id"))
    # Many-to-one relation from order to customer
    customer: Mapped["Customer"] = db.relationship(back_populates="orders")
    # Many to many with product, with no back populates
    products: Mapped[List["Product"]] = db.relationship(secondary=order_product)

class Product(Base):
    __tablename__ = "Products"
    product_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    price: Mapped[float] = mapped_column(db.Float, nullable=False)

# using context manager to create tables in our db
with app.app_context():
    # db.drop_all() drop all tables currently in the database
    db.create_all() #create tables if they dont exist, if they do exist, it does nothing


# Customer Schema
class CustomerSchema(ma.Schema):
    customer_id = fields.Integer()
    name = fields.String(required=True)
    email = fields.String(required=True)
    phone = fields.String(required=True)

    class Meta:
        # fields to expose (what is displayed during a GET request)
        fields = ("customer_id", "email", "name", "phone")

# instantiating our Schemas
customer_schema = CustomerSchema()
customers_schema = CustomerSchema(many=True)


# ======================================== API ROUTES ======================================================
# CUSTOMERS
# get all customers
@app.route("/register", methods=["POST"])
def register():
    try:
        data = account_schema.load(request.json)
    except ValidationError as e:
        return jsonify(e.messages), 400
    
    with Session(db.engine) as session:
        account = session.query(CustomerAccount).filter_by(username=data['username']).first()
        if account and account.check_password(data['password']):
            token = jwt.encode({
                'username': account.username,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            }, 'SECRET_KEY', algorithm='HS256')
            return jsonify({'token': token}), 200
        
        return jsonify({'error': 'Invalid username or password'}), 401

@app.route("/customers", methods = ["GET"])
def get_customers():
    query = select(Customer) #using the select method from our ORM(SQLAlchemy) 
    # to run a SELECT query == SELECT * FROM Customers
    # uses the python class as representation for the Customers table
    result = db.session.execute(query).scalars() # returns a list of customer objects (instances of the customer class)
    # rather than a list of rows or tuples
    customers = result.all() #fetches all rows of data from the result

    # convert to json through the instance of the CustomerSchema class
    return customers_schema.jsonify(customers)

@app.route("/customers/<int:customer_id>", methods=["GET"])
def get_customer_by_id(customer_id):
    customer = db.session.query(Customer).get(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    return customer_schema.jsonify(customer)

# add a customer
@app.route("/customers", methods = ["POST"])
def add_customer():
    try:
        # validate the incoming data from the request
        # making sure it adheres to our schema
        customer_data = customer_schema.load(request.json)
    
    except ValidationError as err:
        return jsonify(err.messages), 400 #Bad Request - insufficient data or mismatched type
    
    # start the db session using the Session import
    # instantiate the Session class with a context manager
    with Session(db.engine) as session: #temporarily instantiates Session to get access to a session object 
        with session.begin(): #Start the db transaction to post data
            name = customer_data['name']
            email = customer_data['email']
            phone = customer_data['phone']

            new_customer = Customer(name=name, email=email, phone=phone) 
            # INSERT INTO Customers (name, email, phone) VALUES(%s, %s, %s)
            # new_customer = (name, email, phone)
            session.add(new_customer)
            session.commit()
    
    return jsonify({"message": "New Customer successfully added!"}), 201 # new resource was created
    
# UPDATE a Customer
@app.route("/customers/<int:id>", methods=["PUT"])
def update_customer(id):
    with Session(db.engine) as session:
        with session.begin():
            # select the customer who's data we'd like to update
            #                         WHERE customer_id = id
            query = select(Customer).filter(Customer.customer_id == id)
            # grabbing the first first result from scalars, returning the object out of the list of results
            result = session.execute(query).scalars().first()
            if result is None:
                return jsonify({"message": "Customer not found"}), 404 # resource not found
            
            # setting a variable to the result
            customer = result
            

            try: 
                # validate incoming data to update the customer object above
                customer_data = customer_schema.load(request.json)
            except ValidationError as err:
                return jsonify(err.messages), 400 #Bad Request
            
            # update the customer object with the values from the incoming data
            # and then commit the changes
            for field, value in customer_data.items():
                setattr(customer, field, value)

            session.commit() #commits the transaction

    return jsonify({"message": "Customer details updated successfully"}), 200 #Successful request


@app.route("/customers/<int:id>", methods=["DELETE"])
def delete_customer(id):
    # delete_statement = delete(Customer).where(Customer.customer_id == id)
    with Session(db.engine) as session:
        with session.begin():
            query = select(Customer).filter(Customer.customer_id == id)
            result = session.execute(query).scalars().first()
            
            if result is None:
                return jsonify({"error": "Customer not found..."}), 404 #not found
            
            session.delete(result) #delete within the session
            session.commit()
            # delete_statement = delete(Customer).where(Customer.customer_id == id)

            # result = db.session.execute(delete_statement)
            # print(result)
            # print(result.rowcount)

            # if result.rowcount == 0:
            #     return jsonify({"error": "Customer not found."}), 404

    return jsonify({"message": "Customer removed successfully!"}), 200

# CustomerAccount Schema
class CustomerAccountSchema(Schema):
    account_id = fields.Integer(dump_only=True)
    username = fields.String(required=True)
    password = fields.String(required=True)
    customer_id = fields.Integer(required=True)

    class Meta:
        fields = ("account_id", "username", "password", "customer_id")

# Instantiate the schema
account_schema = CustomerAccountSchema()
accounts_schema = CustomerAccountSchema(many=True)

@app.route("/customeraccounts", methods=["POST"])
def add_customer_account():
    try:
        customer_account_data = account_schema.load(request.json)
    except ValidationError as e:
        return jsonify(e.messages), 400
    
    with Session(db.engine) as session:
        with session.begin():
            new_account = CustomerAccount(**customer_account_data)
            session.add(new_account)
            session.commit()

    return jsonify({"message": "New Customer Account successfully added!"}), 201

@app.route("/customeraccounts/<int:account_id>", methods=["PUT"])
def update_customer_account(account_id):
    with Session(db.engine) as session:
        with session.begin():
            query = select(CustomerAccount).filter_by(account_id=account_id)
            result = session.execute(query).scalars().first()
            
            if result is None:
                return jsonify({"message": "Customer Account not found"}), 404
            
            try:
                customer_account_data = account_schema.load(request.json)
            except ValidationError as e:
                return jsonify(e.messages), 400
            
            for field, value in customer_account_data.items():
                setattr(result, field, value)

            session.commit()

    return jsonify({"message": "Customer Account details updated successfully"}), 200

@app.route("/customeraccounts/<int:account_id>", methods=["DELETE"])
def delete_customer_account(account_id):
    with Session(db.engine) as session:
        with session.begin():
            query = select(CustomerAccount).filter(CustomerAccount.account_id == account_id)
            result = session.execute(query).scalars().first()
            
            if result is None:
                return jsonify({"message": "Customer Account not found"}), 404
            
            session.delete(result)
            session.commit()

    return jsonify({"message": "Customer Account successfully deleted"}), 200

class ProductSchema(Schema):
    product_id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    price = fields.Float(required=True)

    class Meta:
        fields = ("product_id", "name", "price")

# Instantiate the schema
product_schema = ProductSchema()
products_schema = ProductSchema(many=True)

with app.app_context():
    db.create_all()

@app.route("/products", methods=["GET"])
def get_products():
    query = select(Product)
    result = db.session.execute(query).scalars().all()
    serialized_products = products_schema.dump(result)
    return jsonify(serialized_products), 200

@app.route("/products/<int:product_id>", methods=["GET"])
def get_product_by_id(product_id):
    query = select(Product).filter(Product.product_id == product_id)
    result = db.session.execute(query).scalar()
    if result is None:
        return jsonify({"error": "Product not found"}), 404
    serialized_product = product_schema.dump(result)
    return jsonify(serialized_product), 200

@app.route("/products", methods=["POST"])
def add_product():
    try:
        product_data = product_schema.load(request.json)
    except ValidationError as err:
        return jsonify(err.messages), 400
  
    with Session(db.engine) as session:
        with session.begin():
            new_product = Product(**product_data)
            session.add(new_product)
            product_id = new_product.product_id
    
    
    return jsonify({"message": "New product added successfully!", "product_id": product_id}), 201
   

@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    try:
        product_data = product_schema.load(request.json)
    except ValidationError as err:
        return jsonify(err.messages), 400
    
    try:
        with Session(db.engine) as session:
            product = session.query(Product).get(product_id)
            if not product:
                return jsonify({"error": "Product not found"}), 404
            
            for key, value in product_data.items():
                setattr(product, key, value)
        
            session.commit()
    
        return jsonify({"message": "Product updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    try:
        delete_statement = delete(Product).where(Product.product_id == product_id)
        with db.session.begin():
            result = db.session.execute(delete_statement)
            if result.rowcount == 0:
                return jsonify({"error": f"Product with ID {product_id} doesn't exist!"}), 404

        return jsonify({"message": "Product deleted successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# Order Schema
class OrderSchema(Schema):
    order_id = fields.Integer(dump_only=True)
    customer_id = fields.Integer(required=True)
    date = fields.Date(required=True)
    products = fields.List(fields.Integer())  # List of product IDs

    class Meta:
        fields = ("order_id", "customer_id", "date", "products")

# Instantiate the schema
order_schema = OrderSchema()
orders_schema = OrderSchema(many=True)


@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        query = select(Order)
        with Session(db.engine) as session:
            orders = session.execute(query).scalars().all()
            
            # Manually serialize orders to handle related objects
            orders_list = []
            for order in orders:
                order_dict = {
                    "order_id": order.order_id,
                    "customer_id": order.customer_id,
                    "date": order.date,
                    "products": [product.product_id for product in order.products]  # Convert Product objects to IDs
                }
                orders_list.append(order_dict)
            
            return jsonify(orders_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/orders", methods=["POST"])
def add_order():
    try:
        order_data = order_schema.load(request.json)
    except ValidationError as err:
        return jsonify(err.messages), 400
    
    try:
        with Session(db.engine) as session:
            # Check if the customer exists
            customer_query = select(Customer).filter(Customer.customer_id == order_data['customer_id'])
            customer = session.execute(customer_query).scalar()
            if not customer:
                return jsonify({"error": "Customer not found"}), 404

            new_order = Order(
                customer_id=order_data['customer_id'],
                date=order_data['date']
            )
            # Add products if provided
            for product_id in order_data.get('products', []):
                product = session.execute(select(Product).filter(Product.product_id == product_id)).scalar()
                if product:
                    new_order.products.append(product)
                else:
                    return jsonify({"error": f"Product with ID {product_id} not found"}), 404
            
            session.add(new_order)
            session.commit()
        return jsonify({"message": "Order added successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
        
            
        

        
 
@app.route('/orders/<int:order_id>', methods=["PUT"])
def update_order(order_id):
    try:
        json_order = request.json
        products = json_order.pop('products', None)
        
        order_data = order_schema.load(json_order, partial=True)
    except ValidationError as err:
        return jsonify(err.messages), 400
    
    with Session(db.engine) as session:
        with session.begin():
            query = select(Order).filter(Order.order_id == order_id)
            result = session.execute(query).scalar()
            if result is None:
                return jsonify({"message": "Order Not Found"}), 404
            
            order = result
            
            for field, value in order_data.items():
                setattr(order, field, value)
            
            if products is not None:
                order.products.clear()
                for id in products:
                    product = session.execute(select(Product).filter(Product.product_id == id)).scalar()
                    if product:
                        order.products.append(product)
                    else:
                        return jsonify({"error": f"Product with ID {id} not found"}), 404

            session.commit()
            
    return jsonify({"message": "Order was successfully updated!"}), 200

@app.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    delete_statement = delete(Order).where(Order.order_id == order_id)
    with db.session.begin():
        result = db.session.execute(delete_statement)
        if result.rowcount == 0:
            return jsonify({"error": f"Order with ID {order_id} doesn't exist!"}), 404
        return jsonify({"message": "Order deleted successfully!"}), 200



    

    










@app.route("/")
def home():
    return "<h1>This a tasty api (ヘ･_･)ヘ┳━┳  (╯°□°）╯︵ ┻━┻</h1>"



if __name__ == "__main__": #check that the file we're in is the file thats being run
    app.run(debug=True) #if so we run our application and turn on the debugger

    