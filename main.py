"""
Medicine Expiry & Stock Alert System
=====================================
Python + CSV mini project.

Features:
  1  Add Medicine
  2  Display All Medicines
  3  Search Medicine
  4  Expiry Alert
  5  Stock Alert
  6  Update Medicine         (with Restock Log)
  7  Delete Medicine
  8  Generate Report
  9  Import / Export CSV
  10 Supplier Details
  11 View Restock Log
  12 Exit
"""

from medicine_store import (
    add_medicine,
    display_medicines,
    search_medicine,
    expiry_alert,
    stock_alert,
    update_medicine,
    delete_medicine,
    generate_report,
    import_export_menu,
    supplier_menu,
    view_restock_log,
)

MENU = """
+--------------------------------------------------+
|     Medicine Expiry & Stock Alert System         |
+--------------------------------------------------+
|  1.  Add Medicine                                |
|  2.  Display All Medicines                       |
|  3.  Search Medicine                             |
|  4.  Expiry Alert                                |
|  5.  Stock Alert                                 |
|  6.  Update Medicine                             |
|  7.  Delete Medicine                             |
+--------------------------------------------------+
|  8.  Generate Report                             |
|  9.  Import / Export CSV                         |
|  10. Supplier Details                            |
|  11. View Restock Log                            |
+--------------------------------------------------+
|  12. Exit                                        |
+--------------------------------------------------+"""

ACTIONS = {
    "1":  add_medicine,
    "2":  display_medicines,
    "3":  search_medicine,
    "4":  expiry_alert,
    "5":  stock_alert,
    "6":  update_medicine,
    "7":  delete_medicine,
    "8":  generate_report,
    "9":  import_export_menu,
    "10": supplier_menu,
    "11": view_restock_log,
}


def main():
    print("\n  Welcome to the Medicine Expiry & Stock Alert System")
    while True:
        print(MENU)
        choice = input("\n  Enter your choice (1-12): ").strip()

        if choice == "12":
            print("\n  Goodbye! Stay healthy.\n")
            break
        elif choice in ACTIONS:
            ACTIONS[choice]()
        else:
            print("  x Invalid option. Please enter a number from 1 to 12.")


if __name__ == "__main__":
    main()
