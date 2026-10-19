import os

# =================== WELCOME AND SETUP ===============================

INVENTORY_FILE = "Dictionary.txt"
SALES_FILE = "sales_log.txt"
SOLD_PRODUCTS_FILE = "sold_products.txt"


def ask_kiosk_info():
    kiosk_name = input('Enter the Kiosk name: ').strip().title()
    owner_name = input('Enter the name of the owner: ').strip().title()
    return kiosk_name, owner_name


def show_owner_details(kiosk_name, owner_name):
    print(f"Welcome to {kiosk_name}'s Kiosk Manager, run by {owner_name}")


# =================== SAVING AND LOADING ===============================

def load_inventory():
    """Load stock from the save file, or start with a default inventory."""
    if not os.path.exists(INVENTORY_FILE):
        return {
            "Pen": {"price": 65, "quantity": 20},
            "Books": {"price": 80, "quantity": 15},
            "Print Papers": {"price": 160, "quantity": 10},
        }
    loaded = {}
    with open(INVENTORY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line == "":
                continue
            product, price, quantity = line.split(",")
            loaded[product] = {"price": int(price), "quantity": int(quantity)}
    return loaded


def save_inventory():
    with open(INVENTORY_FILE, 'w') as f:
        for product, details in inventory.items():
            f.write(f"{product},{details['price']},{details['quantity']}\n")
    print('Inventory saved successfully')


def save_sales_log():
    # "a" = append, so earlier sessions are never overwritten
    with open(SALES_FILE, "a") as file:
        for sale in sales_log:
            product, quantity, total = sale
            file.write(f"{product},{quantity},{total}\n")


def save_sold_products():
    with open(SOLD_PRODUCTS_FILE, "w") as file:
        for product in sold_products:
            file.write(f"{product}\n")


# =================== VIEW STOCK ===============================

def view_inventory():
    if not inventory:
        print("Inventory is empty.")
        return
    print("\nINVENTORY")
    print("-" * 40)
    print(f"{'Product':<15}{'Price':<12}{'Quantity':<10}")
    print("-" * 40)
    for product, details in inventory.items():
        print(f"{product:<15}{details['price']:<12}{details['quantity']:<10}")
    print()


# =================== ADD / RESTOCK ===============================

def add_or_restock_product():
    product = input("Enter product name: ").strip().title()

    if product == "" or product.isdigit():
        print("Invalid product name. Please enter a valid product name.")
        return

    if product in inventory:
        quantity = input("Enter quantity to add: ").strip()
        if not quantity.isdigit():
            print("Quantity must be a number.")
            return
        quantity = int(quantity)
        if quantity <= 0:
            print("Quantity must be greater than 0.")
            return
        inventory[product]["quantity"] += quantity
        print(f"{product} has been restocked successfully.")
    else:
        price = input("Enter product price: ").strip()
        quantity = input("Enter product quantity: ").strip()
        if not price.isdigit() or not quantity.isdigit():
            print("Price and quantity must be numbers.")
            return
        price = int(price)
        quantity = int(quantity)
        if price <= 0 or quantity <= 0:
            print("Price and quantity must be greater than 0.")
            return
        inventory[product] = {"price": price, "quantity": quantity}
        print(f"{product} has been added successfully.")


# =================== SELL ===============================

def sell_product():
    product = input('Which product to sell: ').strip().title()

    if product == "" or product.isdigit():
        print("Invalid product name. Please enter a valid product name.")
        return
    if product not in inventory:
        print(f"{product} is not available in the inventory.")
        return

    quantity = input('Enter the units to be sold: ').strip()
    if not quantity.isdigit():
        print('Quantity must be a digit')
        return
    quantity = int(quantity)
    if quantity <= 0:
        print('Quantity should be greater than 0')
        return
    if quantity > inventory[product]["quantity"]:
        print(f"Not enough stock. Only {inventory[product]['quantity']} units available.")
        return

    price = inventory[product]['price']
    total = quantity * price
    inventory[product]["quantity"] -= quantity

    sale = (product, quantity, total)   # a tuple
    sales_log.append(sale)              # into a list
    sold_products.add(product)          # and the product into a set

    print("Sale successful.")
    print(f"Product: {product}")
    print(f"Quantity: {quantity}")
    print(f"Total: KES {total}")


# =================== SALES REPORT ===============================

def sales_report():
    if not sales_log:
        print("No sales yet this session.")
        return

    print("\nSALES REPORT")
    print("-" * 40)
    print(f"{'Product':<15}{'Quantity':<10}{'Total (KES)':<12}")
    print("-" * 40)

    revenue = 0
    units_by_product = {}
    for product, quantity, total in sales_log:
        print(f"{product:<15}{quantity:<10}{total:<12}")
        revenue += total
        units_by_product[product] = units_by_product.get(product, 0) + quantity

    best = max(units_by_product, key=units_by_product.get)
    print("-" * 40)
    print(f"Total revenue: KES {revenue}")
    print(f"Unique products sold: {len(sold_products)}")
    print(f"Best seller: {best} ({units_by_product[best]} units)\n")


# =================== SEARCH ===============================

def search_products():
    term = input("Search for a product: ").strip().lower()
    if term == "":
        print("Please type something to search for.")
        return

    found = False
    for product, details in inventory.items():
        if term in product.lower():
            print(f"{product:<15}KES {details['price']:<8}Qty: {details['quantity']}")
            found = True
    if not found:
        print("No matches found.")


# =================== MAIN PROGRAM ===============================

kiosk_name, owner_name = ask_kiosk_info()
show_owner_details(kiosk_name, owner_name)
print()

inventory = load_inventory()
sales_log = []
sold_products = set()

while True:
    print('==============MAIN MENU============== ')
    print('1. View Stock')
    print('2. Add/ Restock a Product')
    print('3. Sell a Product')
    print('4. View Sales Report')
    print('5. Search Products')
    print('6. Exit')

    choice = input('Enter your choice (Between 1 and 6): ').strip()

    if not choice.isdigit():
        print('Invalid choice. Please enter a number between 1 and 6')
        continue
    choice = int(choice)
    if choice < 1 or choice > 6:
        print('Invalid choice. Please enter a number between 1 and 6')
        continue

    if choice == 1:
        view_inventory()
    elif choice == 2:
        add_or_restock_product()
    elif choice == 3:
        sell_product()
    elif choice == 4:
        sales_report()
    elif choice == 5:
        search_products()
    else:
        save_inventory()
        save_sales_log()
        save_sold_products()
        print(f'Exiting. Goodbye, {owner_name}!')
        break
