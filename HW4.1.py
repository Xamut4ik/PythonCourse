class Product():
    def __init__(self, name, category, price, quantity):
        self.name = name
        self.category = category
        self.price = price
        self.quantity = quantity

    def price_change(self, new_price):
        self.price = new_price
        print(f"Нова ціна - {self.price}")

    def quantity_change(self, new_quantity):
        self.quantity = new_quantity
        print(f"Нова кількість на складі - {self.quantity}")

    def __str__(self):
        return f"{self.name} | {self.category} | {self.price} грн | {self.quantity} шт."


class Customer():
    def __init__(self, name, email, order_list):
        self.name = name
        self.email = email
        self.order_list = order_list


    def new_order(self, new_order):
        self.order_list.append(new_order)
        print(f"Ваші замовлення - {self.order_list}")

    def __str__(self):
        orders1 = "\n".join(str(order) for order in self.order_list)
        return f"{self.name} | {self.email} | {orders1}"



class Order():
    def __init__(self, product_list, order_value):
        self.product_list = product_list
        self.order_value = order_value

    def new_product(self, new_product):
        self.product_list.append(new_product)
        print(f"Новий товар - {self.product_list}")

    def total_value(self, new_order_value):
        self.order_value = 0
        for product in self.product_list:
            self.order_value += product.price
        print(f"Нова сума замовлення - {self.order_value}")

    def __str__(self):
        return f"{self.product_list} | {self.order_value}"

products = []

with open("products.txt", encoding="utf-8") as file:
    for line in file:
        name, category, price, quantity = line.strip().split(";")
        products.append(Product(name, category, float(price), int(quantity)))


orders = []

with open("orders.txt", encoding="utf-8") as file:
    for line in file:
        product_list, order_value = line.strip().split(";")
        orders.append(Order(product_list, order_value))


customers = []

with open("customers.txt", encoding="utf-8") as file:
    for i, line in enumerate(file):
        name, email, order_value = line.strip().split(";")
        customers.append(Customer(name, email, [orders[i]]))


for product in products:
    print(product)

for customer in customers:
    print(customer)

for order in orders:
    print(order)