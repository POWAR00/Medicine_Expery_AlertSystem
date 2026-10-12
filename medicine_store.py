import csv
import os
from datetime import datetime, date

# ─────────────────────────────────────────────
# File Paths & Constants
# ─────────────────────────────────────────────

_DIR = os.path.dirname(__file__)
CSV_FILE      = os.path.join(_DIR, "medicines.csv")
SUPPLIER_FILE = os.path.join(_DIR, "suppliers.csv")
RESTOCK_FILE  = os.path.join(_DIR, "restock_log.csv")

FIELDNAMES = [
    "medicine_id", "medicine_name", "batch_number",
    "quantity", "expiry_date", "price"
]
SUPPLIER_FIELDS = ["medicine_id", "supplier_name", "contact_number", "email"]
RESTOCK_FIELDS  = ["timestamp", "medicine_id", "medicine_name",
                   "old_quantity", "new_quantity", "changed_by"]

MIN_STOCK_LEVEL = 10
DATE_FORMAT     = "%Y-%m-%d"
TS_FORMAT       = "%Y-%m-%d %H:%M:%S"


# ─────────────────────────────────────────────
# CSV Helpers — Medicines
# ─────────────────────────────────────────────

def _load_medicines():
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_medicines(medicines):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(medicines)


# ─────────────────────────────────────────────
# CSV Helpers — Suppliers
# ─────────────────────────────────────────────

def _load_suppliers():
    if not os.path.exists(SUPPLIER_FILE):
        return []
    with open(SUPPLIER_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_suppliers(suppliers):
    with open(SUPPLIER_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUPPLIER_FIELDS)
        writer.writeheader()
        writer.writerows(suppliers)


def _get_supplier(med_id):
    """Return supplier dict for a medicine_id, or None."""
    for s in _load_suppliers():
        if s["medicine_id"].strip().lower() == med_id.strip().lower():
            return s
    return None


# ─────────────────────────────────────────────
# CSV Helpers — Restock Log
# ─────────────────────────────────────────────

def _append_restock_log(entry):
    file_exists = os.path.exists(RESTOCK_FILE)
    with open(RESTOCK_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESTOCK_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


def _load_restock_log():
    if not os.path.exists(RESTOCK_FILE):
        return []
    with open(RESTOCK_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ─────────────────────────────────────────────
# Input Helpers
# ─────────────────────────────────────────────

def _input_nonempty(prompt):
    while True:
        val = input(prompt).strip()
        if val:
            return val
        print("  x This field cannot be empty.")


def _input_positive_int(prompt):
    while True:
        val = input(prompt).strip()
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  x Please enter a positive whole number.")


def _input_positive_float(prompt):
    while True:
        val = input(prompt).strip()
        try:
            f = float(val)
            if f > 0:
                return round(f, 2)
        except ValueError:
            pass
        print("  x Please enter a valid positive number.")


def _input_date(prompt):
    while True:
        val = input(prompt).strip()
        try:
            datetime.strptime(val, DATE_FORMAT)
            return val
        except ValueError:
            print("  x Invalid date. Use YYYY-MM-DD format (e.g. 2025-12-31).")


def _id_exists(medicines, med_id):
    return any(m["medicine_id"].strip().lower() == med_id.strip().lower() for m in medicines)


# ─────────────────────────────────────────────
# Display Helpers
# ─────────────────────────────────────────────

COL = 100

def _divider(char="-", width=COL):
    print(char * width)

def _print_table(medicines):
    if not medicines:
        print("  (no records to display)")
        return
    _divider()
    print(
        f"{'ID':<12} {'Name':<22} {'Batch':<14} {'Qty':>6}  "
        f"{'Expiry':<14} {'Price':>10}  {'Supplier':<20} {'Contact':<15}"
    )
    _divider()
    today = date.today()
    suppliers = {s["medicine_id"].strip().lower(): s for s in _load_suppliers()}
    for m in medicines:
        exp = datetime.strptime(m["expiry_date"], DATE_FORMAT).date()
        days_left = (exp - today).days
        tag = ""
        if days_left < 0:
            tag = " [EXPIRED]"
        elif days_left <= 30:
            tag = f" [exp {days_left}d]"

        qty = int(m["quantity"])
        qty_tag = "*" if qty <= MIN_STOCK_LEVEL else " "

        sup = suppliers.get(m["medicine_id"].strip().lower(), {})
        sup_name    = sup.get("supplier_name", "-")[:20]
        sup_contact = sup.get("contact_number", "-")[:15]

        print(
            f"{m['medicine_id']:<12} {m['medicine_name']:<22} {m['batch_number']:<14}"
            f" {qty:>5}{qty_tag}  {m['expiry_date']:<14} {float(m['price']):>9.2f}  "
            f"{sup_name:<20} {sup_contact:<15}{tag}"
        )
    _divider()
    print("  * = low stock")


# ─────────────────────────────────────────────
# 1. Add Medicine
# ─────────────────────────────────────────────

def add_medicine():
    print("\n-- Add Medicine --")
    medicines = _load_medicines()

    med_id = _input_nonempty("  Medicine ID          : ")
    if _id_exists(medicines, med_id):
        print(f"  x Medicine ID '{med_id}' already exists.")
        return

    name     = _input_nonempty("  Medicine Name        : ")
    batch    = _input_nonempty("  Batch Number         : ")
    quantity = _input_positive_int("  Quantity             : ")
    expiry   = _input_date("  Expiry Date (YYYY-MM-DD): ")
    price    = _input_positive_float("  Price                : ")

    medicines.append({
        "medicine_id":   med_id,
        "medicine_name": name,
        "batch_number":  batch,
        "quantity":      quantity,
        "expiry_date":   expiry,
        "price":         price,
    })
    _save_medicines(medicines)

    # Optional supplier details
    add_sup = input("\n  Add supplier details for this medicine? (yes/no): ").strip().lower()
    if add_sup == "yes":
        _save_supplier_for(med_id)

    print(f"  + Medicine '{name}' added successfully.")


# ─────────────────────────────────────────────
# 2. Display All Medicines
# ─────────────────────────────────────────────

def display_medicines():
    print("\n-- All Medicines --")
    medicines = _load_medicines()
    if not medicines:
        print("  No medicines found in the system.")
        return
    _print_table(medicines)
    print(f"  Total records: {len(medicines)}")


# ─────────────────────────────────────────────
# 3. Search Medicine
# ─────────────────────────────────────────────

def search_medicine():
    print("\n-- Search Medicine --")
    keyword = _input_nonempty("  Enter Medicine ID or Name: ").lower()
    medicines = _load_medicines()
    results = [
        m for m in medicines
        if keyword in m["medicine_id"].lower() or keyword in m["medicine_name"].lower()
    ]
    if results:
        print(f"  Found {len(results)} result(s):")
        _print_table(results)
    else:
        print(f"  No medicine found matching '{keyword}'.")


# ─────────────────────────────────────────────
# 4. Expiry Alert
# ─────────────────────────────────────────────

def expiry_alert():
    print("\n-- Expiry Alert --")
    medicines = _load_medicines()
    today = date.today()

    days_str = input("  Expiring within how many days? (default 30): ").strip()
    threshold = int(days_str) if days_str.isdigit() else 30

    expired = []
    expiring_soon = []
    for m in medicines:
        exp = datetime.strptime(m["expiry_date"], DATE_FORMAT).date()
        days_left = (exp - today).days
        if days_left < 0:
            expired.append(m)
        elif days_left <= threshold:
            expiring_soon.append(m)

    print(f"\n  [X] Expired Medicines ({len(expired)}):")
    _print_table(expired)
    print(f"\n  [!] Expiring within {threshold} days ({len(expiring_soon)}):")
    _print_table(expiring_soon)


# ─────────────────────────────────────────────
# 5. Stock Alert
# ─────────────────────────────────────────────

def stock_alert():
    print("\n-- Stock Alert --")
    level_str = input(f"  Minimum stock threshold (default {MIN_STOCK_LEVEL}): ").strip()
    threshold = int(level_str) if level_str.isdigit() else MIN_STOCK_LEVEL

    medicines = _load_medicines()
    low_stock = [m for m in medicines if int(m["quantity"]) <= threshold]

    print(f"\n  [!] Medicines with stock <= {threshold} units ({len(low_stock)}):")
    _print_table(low_stock)


# ─────────────────────────────────────────────
# 6. Update Medicine  (with restock log)
# ─────────────────────────────────────────────

def update_medicine():
    print("\n-- Update Medicine --")
    medicines = _load_medicines()
    med_id = _input_nonempty("  Enter Medicine ID to update: ")

    target = None
    for m in medicines:
        if m["medicine_id"].strip().lower() == med_id.strip().lower():
            target = m
            break

    if not target:
        print(f"  x Medicine ID '{med_id}' not found.")
        return

    print(f"\n  Updating: {target['medicine_name']} (Batch: {target['batch_number']})")
    print("  Leave blank to keep current value.\n")

    old_qty = int(target["quantity"])

    new_qty    = input(f"  Quantity    [{target['quantity']}]: ").strip()
    new_price  = input(f"  Price       [{target['price']}]: ").strip()
    new_expiry = input(f"  Expiry Date [{target['expiry_date']}] (YYYY-MM-DD): ").strip()
    changed_by = input(f"  Changed by  (your name/ID):  ").strip() or "system"

    qty_changed = False
    if new_qty:
        if new_qty.isdigit() and int(new_qty) > 0:
            target["quantity"] = new_qty
            qty_changed = True
        else:
            print("  x Invalid quantity — keeping original.")

    if new_price:
        try:
            fp = float(new_price)
            if fp > 0:
                target["price"] = round(fp, 2)
            else:
                print("  x Invalid price — keeping original.")
        except ValueError:
            print("  x Invalid price — keeping original.")

    if new_expiry:
        try:
            datetime.strptime(new_expiry, DATE_FORMAT)
            target["expiry_date"] = new_expiry
        except ValueError:
            print("  x Invalid date — keeping original.")

    _save_medicines(medicines)

    # Log quantity change
    if qty_changed:
        _append_restock_log({
            "timestamp":    datetime.now().strftime(TS_FORMAT),
            "medicine_id":  target["medicine_id"],
            "medicine_name": target["medicine_name"],
            "old_quantity": old_qty,
            "new_quantity": int(target["quantity"]),
            "changed_by":   changed_by,
        })
        print(f"  + Restock log entry saved.")

    print(f"  + Medicine '{target['medicine_name']}' updated successfully.")


# ─────────────────────────────────────────────
# 7. Delete Medicine
# ─────────────────────────────────────────────

def delete_medicine():
    print("\n-- Delete Medicine --")
    medicines = _load_medicines()
    med_id = _input_nonempty("  Enter Medicine ID to delete: ")

    match = [m for m in medicines if m["medicine_id"].strip().lower() == med_id.strip().lower()]
    if not match:
        print(f"  x Medicine ID '{med_id}' not found.")
        return

    name = match[0]["medicine_name"]
    confirm = input(f"  Are you sure you want to delete '{name}'? (yes/no): ").strip().lower()
    if confirm == "yes":
        medicines = [m for m in medicines if m["medicine_id"].strip().lower() != med_id.strip().lower()]
        _save_medicines(medicines)
        # Remove supplier entry too
        suppliers = [s for s in _load_suppliers() if s["medicine_id"].strip().lower() != med_id.strip().lower()]
        _save_suppliers(suppliers)
        print(f"  + Medicine '{name}' (and its supplier record) deleted successfully.")
    else:
        print("  Deletion cancelled.")


# ─────────────────────────────────────────────
# 8. Generate Report
# ─────────────────────────────────────────────

def generate_report():
    print("\n-- Generate Summary Report --")
    medicines = _load_medicines()
    today = date.today()

    if not medicines:
        print("  No medicines found.")
        return

    total_count  = len(medicines)
    total_value  = sum(float(m["price"]) * int(m["quantity"]) for m in medicines)
    expired      = [m for m in medicines if (datetime.strptime(m["expiry_date"], DATE_FORMAT).date() - today).days < 0]
    expiring_30  = [m for m in medicines if 0 <= (datetime.strptime(m["expiry_date"], DATE_FORMAT).date() - today).days <= 30]
    low_stock    = [m for m in medicines if int(m["quantity"]) <= MIN_STOCK_LEVEL]

    _divider("=")
    print("  MEDICINE STOCK SUMMARY REPORT")
    print(f"  Generated on : {today.strftime('%d %B %Y')}")
    _divider("=")
    print(f"  Total Medicines      : {total_count}")
    print(f"  Total Inventory Value: Rs. {total_value:,.2f}")
    print(f"  Expired              : {len(expired)}")
    print(f"  Expiring in 30 days  : {len(expiring_30)}")
    print(f"  Low Stock (<=10)     : {len(low_stock)}")
    _divider()

    if expired:
        print("\n  [X] Expired Medicines:")
        for m in expired:
            print(f"      {m['medicine_id']} | {m['medicine_name']} | Exp: {m['expiry_date']} | Qty: {m['quantity']}")

    if expiring_30:
        print("\n  [!] Expiring Within 30 Days:")
        for m in expiring_30:
            exp = datetime.strptime(m["expiry_date"], DATE_FORMAT).date()
            days = (exp - today).days
            print(f"      {m['medicine_id']} | {m['medicine_name']} | Exp: {m['expiry_date']} | Days left: {days}")

    if low_stock:
        print("\n  [!] Low Stock Medicines:")
        for m in low_stock:
            print(f"      {m['medicine_id']} | {m['medicine_name']} | Qty: {m['quantity']}")

    # Save report to file
    save = input("\n  Save this report to a text file? (yes/no): ").strip().lower()
    if save == "yes":
        report_path = os.path.join(_DIR, f"report_{today.strftime('%Y%m%d')}.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("MEDICINE STOCK SUMMARY REPORT\n")
            f.write(f"Generated on : {today.strftime('%d %B %Y')}\n")
            f.write("-" * 60 + "\n")
            f.write(f"Total Medicines      : {total_count}\n")
            f.write(f"Total Inventory Value: Rs. {total_value:,.2f}\n")
            f.write(f"Expired              : {len(expired)}\n")
            f.write(f"Expiring in 30 days  : {len(expiring_30)}\n")
            f.write(f"Low Stock (<=10)     : {len(low_stock)}\n")
            f.write("-" * 60 + "\n")
            if expired:
                f.write("\nExpired Medicines:\n")
                for m in expired:
                    f.write(f"  {m['medicine_id']} | {m['medicine_name']} | {m['expiry_date']} | Qty:{m['quantity']}\n")
            if expiring_30:
                f.write("\nExpiring in 30 Days:\n")
                for m in expiring_30:
                    f.write(f"  {m['medicine_id']} | {m['medicine_name']} | {m['expiry_date']}\n")
            if low_stock:
                f.write("\nLow Stock:\n")
                for m in low_stock:
                    f.write(f"  {m['medicine_id']} | {m['medicine_name']} | Qty:{m['quantity']}\n")
        print(f"  + Report saved to: {report_path}")


# ─────────────────────────────────────────────
# 9. Import / Export CSV
# ─────────────────────────────────────────────

def import_export_menu():
    print("\n-- Import / Export --")
    print("  1. Import medicines from external CSV")
    print("  2. Export medicines to external CSV")
    choice = input("  Choose (1/2): ").strip()
    if choice == "1":
        _import_medicines()
    elif choice == "2":
        _export_medicines()
    else:
        print("  x Invalid choice.")


def _import_medicines():
    path = _input_nonempty("  Path to CSV file to import: ")
    if not os.path.exists(path):
        print(f"  x File not found: {path}")
        return
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print(f"  x Could not read file: {e}")
        return

    # Validate required columns
    required = set(FIELDNAMES)
    if not required.issubset(set(rows[0].keys()) if rows else set()):
        print(f"  x CSV must have columns: {', '.join(FIELDNAMES)}")
        return

    medicines = _load_medicines()
    added = skipped = 0
    for row in rows:
        if _id_exists(medicines, row["medicine_id"]):
            skipped += 1
        else:
            medicines.append({k: row[k].strip() for k in FIELDNAMES})
            added += 1

    _save_medicines(medicines)
    print(f"  + Import complete — Added: {added}, Skipped (duplicate): {skipped}")


def _export_medicines():
    medicines = _load_medicines()
    if not medicines:
        print("  No medicines to export.")
        return
    out_path = os.path.join(_DIR, f"export_{date.today().strftime('%Y%m%d')}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(medicines)
    print(f"  + Exported {len(medicines)} records to: {out_path}")


# ─────────────────────────────────────────────
# 10. Supplier Details
# ─────────────────────────────────────────────

def supplier_menu():
    print("\n-- Supplier Details --")
    print("  1. Add / Update Supplier for a Medicine")
    print("  2. View All Suppliers")
    print("  3. Delete Supplier Record")
    choice = input("  Choose (1/2/3): ").strip()
    if choice == "1":
        med_id = _input_nonempty("  Medicine ID: ")
        medicines = _load_medicines()
        if not _id_exists(medicines, med_id):
            print(f"  x Medicine ID '{med_id}' does not exist.")
            return
        _save_supplier_for(med_id)
    elif choice == "2":
        _view_suppliers()
    elif choice == "3":
        _delete_supplier()
    else:
        print("  x Invalid choice.")


def _save_supplier_for(med_id):
    suppliers = _load_suppliers()
    name    = _input_nonempty("  Supplier Name   : ")
    contact = _input_nonempty("  Contact Number  : ")
    email   = input("  Email (optional): ").strip()

    # Update if already exists, else append
    updated = False
    for s in suppliers:
        if s["medicine_id"].strip().lower() == med_id.strip().lower():
            s["supplier_name"]    = name
            s["contact_number"]   = contact
            s["email"]            = email
            updated = True
            break
    if not updated:
        suppliers.append({"medicine_id": med_id, "supplier_name": name,
                          "contact_number": contact, "email": email})
    _save_suppliers(suppliers)
    print(f"  + Supplier info saved for medicine ID '{med_id}'.")


def _view_suppliers():
    suppliers = _load_suppliers()
    medicines = {m["medicine_id"].strip().lower(): m["medicine_name"] for m in _load_medicines()}
    if not suppliers:
        print("  No supplier records found.")
        return
    _divider()
    print(f"  {'Med ID':<12} {'Medicine Name':<22} {'Supplier':<22} {'Contact':<16} {'Email'}")
    _divider()
    for s in suppliers:
        med_name = medicines.get(s["medicine_id"].strip().lower(), "Unknown")
        print(f"  {s['medicine_id']:<12} {med_name:<22} {s['supplier_name']:<22} {s['contact_number']:<16} {s.get('email','')}")
    _divider()


def _delete_supplier():
    med_id = _input_nonempty("  Medicine ID to remove supplier: ")
    suppliers = _load_suppliers()
    new_list = [s for s in suppliers if s["medicine_id"].strip().lower() != med_id.strip().lower()]
    if len(new_list) == len(suppliers):
        print(f"  x No supplier found for ID '{med_id}'.")
    else:
        _save_suppliers(new_list)
        print(f"  + Supplier record deleted for '{med_id}'.")


# ─────────────────────────────────────────────
# 11. Restock Log
# ─────────────────────────────────────────────

def view_restock_log():
    print("\n-- Restock Log --")
    log = _load_restock_log()
    if not log:
        print("  No restock entries found.")
        return

    filter_id = input("  Filter by Medicine ID (leave blank for all): ").strip().lower()
    if filter_id:
        log = [e for e in log if e["medicine_id"].strip().lower() == filter_id]

    if not log:
        print("  No entries match that filter.")
        return

    _divider()
    print(f"  {'Timestamp':<22} {'Med ID':<12} {'Medicine Name':<22} {'Old Qty':>8} {'New Qty':>8} {'Change':>8}  {'By'}")
    _divider()
    for e in log:
        old = int(e["old_quantity"])
        new = int(e["new_quantity"])
        diff = new - old
        diff_str = f"+{diff}" if diff >= 0 else str(diff)
        print(
            f"  {e['timestamp']:<22} {e['medicine_id']:<12} {e['medicine_name']:<22}"
            f" {old:>8} {new:>8} {diff_str:>8}  {e['changed_by']}"
        )
    _divider()
    print(f"  Total log entries shown: {len(log)}")
