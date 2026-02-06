#!/usr/bin/env python3
"""
KameleonDB 1GB Stress Test

Tests both SQLite and PostgreSQL with ~1GB of data.
Measures: insert, materialize, query, dematerialize performance.

Usage:
    python scripts/stress_test_1gb.py --sqlite-only
    python scripts/stress_test_1gb.py --postgres-url postgresql://user:pass@localhost/testdb
    python scripts/stress_test_1gb.py --both --postgres-url postgresql://...
"""

import argparse
import json
import os
import random
import string
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kameleondb import KameleonDB


# =============================================================================
# Data Generation
# =============================================================================

def random_string(length: int) -> str:
    """Generate random string."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def random_email() -> str:
    """Generate random email."""
    return f"{random_string(8)}@{random_string(6)}.com"


def random_date(start_year: int = 2020, end_year: int = 2025) -> str:
    """Generate random date string."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).isoformat()


def generate_customer(customer_id: int) -> dict:
    """Generate a customer record (~500 bytes)."""
    return {
        "customer_id": customer_id,
        "email": random_email(),
        "first_name": random_string(10),
        "last_name": random_string(12),
        "company": random_string(20) if random.random() > 0.3 else None,
        "phone": f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
        "address": {
            "street": f"{random.randint(1, 9999)} {random_string(15)} St",
            "city": random_string(12),
            "state": random_string(2).upper(),
            "zip": f"{random.randint(10000, 99999)}",
            "country": "US"
        },
        "created_at": random_date(),
        "tier": random.choice(["bronze", "silver", "gold", "platinum"]),
        "lifetime_value": round(random.uniform(100, 50000), 2),
        "notes": random_string(100) if random.random() > 0.5 else None
    }


def generate_product(product_id: int) -> dict:
    """Generate a product record (~400 bytes)."""
    categories = ["Electronics", "Clothing", "Home", "Sports", "Books", "Toys", "Food", "Beauty"]
    return {
        "product_id": product_id,
        "sku": f"SKU-{random_string(8).upper()}",
        "name": f"{random_string(5)} {random_string(8)} {random_string(6)}".title(),
        "description": random_string(150),
        "category": random.choice(categories),
        "price": round(random.uniform(5, 2000), 2),
        "cost": round(random.uniform(2, 1000), 2),
        "stock_quantity": random.randint(0, 10000),
        "weight_kg": round(random.uniform(0.1, 50), 2),
        "is_active": random.random() > 0.1,
        "created_at": random_date(),
        "tags": [random_string(6) for _ in range(random.randint(1, 5))]
    }


def generate_order(order_id: int, customer_ids: list[int], product_ids: list[int]) -> dict:
    """Generate an order record (~800 bytes)."""
    num_items = random.randint(1, 8)
    items = []
    for _ in range(num_items):
        items.append({
            "product_id": random.choice(product_ids),
            "quantity": random.randint(1, 10),
            "unit_price": round(random.uniform(10, 500), 2),
            "discount": round(random.uniform(0, 0.3), 2)
        })
    
    subtotal = sum(i["unit_price"] * i["quantity"] * (1 - i["discount"]) for i in items)
    tax = round(subtotal * 0.08, 2)
    shipping = round(random.uniform(5, 50), 2)
    
    return {
        "order_id": order_id,
        "customer_id": random.choice(customer_ids),
        "order_date": random_date(2023, 2025),
        "status": random.choice(["pending", "processing", "shipped", "delivered", "cancelled"]),
        "items": items,
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "shipping": shipping,
        "total": round(subtotal + tax + shipping, 2),
        "payment_method": random.choice(["credit_card", "debit_card", "paypal", "bank_transfer"]),
        "shipping_address": {
            "street": f"{random.randint(1, 9999)} {random_string(15)} Ave",
            "city": random_string(12),
            "state": random_string(2).upper(),
            "zip": f"{random.randint(10000, 99999)}",
            "country": "US"
        },
        "notes": random_string(50) if random.random() > 0.7 else None
    }


def estimate_size(records: list[dict]) -> int:
    """Estimate JSON size in bytes."""
    return sum(len(json.dumps(r)) for r in records)


# =============================================================================
# Test Runner
# =============================================================================

class StressTest:
    """1GB stress test runner."""
    
    # Target ~1GB total:
    # - 50,000 customers × 500 bytes = 25 MB
    # - 20,000 products × 400 bytes = 8 MB  
    # - 1,200,000 orders × 800 bytes = 960 MB
    # Total: ~1 GB
    
    NUM_CUSTOMERS = 50_000
    NUM_PRODUCTS = 20_000
    NUM_ORDERS = 1_200_000
    
    BATCH_SIZE = 10_000  # Insert in batches
    
    def __init__(self, db_url: str, label: str):
        self.db_url = db_url
        self.label = label
        self.db: KameleonDB | None = None
        self.results: dict = {
            "label": label,
            "url": db_url.split("@")[-1] if "@" in db_url else db_url,  # Hide credentials
            "metrics": {}
        }
        
    def log(self, msg: str):
        """Print with timestamp and label."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.label}] {msg}")
        
    def setup(self):
        """Initialize database and create schemas."""
        self.log("Connecting to database...")
        self.db = KameleonDB(self.db_url)
        
        # Drop existing entities if any
        for entity in ["Order", "Product", "Customer"]:
            try:
                self.db.drop_entity(entity)
            except Exception:
                pass
        
        self.log("Creating schemas...")
        
        # Customer entity
        self.db.create_entity(
            "Customer",
            fields=[
                {"name": "customer_id", "type": "int", "required": True, "unique": True, "indexed": True},
                {"name": "email", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "first_name", "type": "string", "required": True},
                {"name": "last_name", "type": "string", "required": True},
                {"name": "company", "type": "string"},
                {"name": "phone", "type": "string"},
                {"name": "address", "type": "json"},
                {"name": "created_at", "type": "datetime"},
                {"name": "tier", "type": "string", "indexed": True},
                {"name": "lifetime_value", "type": "float"},
                {"name": "notes", "type": "text"},
            ],
            description="Customer records"
        )
        
        # Product entity
        self.db.create_entity(
            "Product",
            fields=[
                {"name": "product_id", "type": "int", "required": True, "unique": True, "indexed": True},
                {"name": "sku", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "description", "type": "text"},
                {"name": "category", "type": "string", "indexed": True},
                {"name": "price", "type": "float", "required": True},
                {"name": "cost", "type": "float"},
                {"name": "stock_quantity", "type": "int"},
                {"name": "weight_kg", "type": "float"},
                {"name": "is_active", "type": "bool"},
                {"name": "created_at", "type": "datetime"},
                {"name": "tags", "type": "json"},
            ],
            description="Product catalog"
        )
        
        # Order entity
        self.db.create_entity(
            "Order",
            fields=[
                {"name": "order_id", "type": "int", "required": True, "unique": True, "indexed": True},
                {"name": "customer_id", "type": "int", "required": True, "indexed": True},
                {"name": "order_date", "type": "datetime", "indexed": True},
                {"name": "status", "type": "string", "indexed": True},
                {"name": "items", "type": "json", "required": True},
                {"name": "subtotal", "type": "float"},
                {"name": "tax", "type": "float"},
                {"name": "shipping", "type": "float"},
                {"name": "total", "type": "float", "required": True},
                {"name": "payment_method", "type": "string"},
                {"name": "shipping_address", "type": "json"},
                {"name": "notes", "type": "text"},
            ],
            description="Sales orders"
        )
        
        self.log("Schemas created ✓")
        
    def insert_data(self):
        """Insert all test data."""
        total_bytes = 0
        
        # Insert customers
        self.log(f"Generating {self.NUM_CUSTOMERS:,} customers...")
        start = time.time()
        customers = [generate_customer(i) for i in range(1, self.NUM_CUSTOMERS + 1)]
        gen_time = time.time() - start
        customer_bytes = estimate_size(customers)
        total_bytes += customer_bytes
        self.log(f"  Generated in {gen_time:.1f}s ({customer_bytes / 1024 / 1024:.1f} MB)")
        
        self.log(f"Inserting customers...")
        start = time.time()
        customer_entity = self.db.entity("Customer")
        for i in range(0, len(customers), self.BATCH_SIZE):
            batch = customers[i:i + self.BATCH_SIZE]
            customer_entity.insert_many(batch)
            if (i + self.BATCH_SIZE) % 50_000 == 0 or i + self.BATCH_SIZE >= len(customers):
                self.log(f"  {min(i + self.BATCH_SIZE, len(customers)):,} / {len(customers):,}")
        insert_time = time.time() - start
        self.results["metrics"]["customer_insert_seconds"] = insert_time
        self.results["metrics"]["customer_insert_rate"] = len(customers) / insert_time
        self.log(f"  Inserted in {insert_time:.1f}s ({len(customers) / insert_time:,.0f} rec/sec)")
        
        customer_ids = list(range(1, self.NUM_CUSTOMERS + 1))
        
        # Insert products
        self.log(f"Generating {self.NUM_PRODUCTS:,} products...")
        start = time.time()
        products = [generate_product(i) for i in range(1, self.NUM_PRODUCTS + 1)]
        gen_time = time.time() - start
        product_bytes = estimate_size(products)
        total_bytes += product_bytes
        self.log(f"  Generated in {gen_time:.1f}s ({product_bytes / 1024 / 1024:.1f} MB)")
        
        self.log(f"Inserting products...")
        start = time.time()
        product_entity = self.db.entity("Product")
        for i in range(0, len(products), self.BATCH_SIZE):
            batch = products[i:i + self.BATCH_SIZE]
            product_entity.insert_many(batch)
        insert_time = time.time() - start
        self.results["metrics"]["product_insert_seconds"] = insert_time
        self.results["metrics"]["product_insert_rate"] = len(products) / insert_time
        self.log(f"  Inserted in {insert_time:.1f}s ({len(products) / insert_time:,.0f} rec/sec)")
        
        product_ids = list(range(1, self.NUM_PRODUCTS + 1))
        
        # Insert orders (the big one)
        self.log(f"Generating and inserting {self.NUM_ORDERS:,} orders...")
        start = time.time()
        order_bytes = 0
        order_entity = self.db.entity("Order")
        
        for batch_start in range(0, self.NUM_ORDERS, self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, self.NUM_ORDERS)
            orders = [generate_order(i, customer_ids, product_ids) for i in range(batch_start + 1, batch_end + 1)]
            order_bytes += estimate_size(orders)
            order_entity.insert_many(orders)
            
            if (batch_end) % 100_000 == 0 or batch_end >= self.NUM_ORDERS:
                elapsed = time.time() - start
                rate = batch_end / elapsed
                eta = (self.NUM_ORDERS - batch_end) / rate if rate > 0 else 0
                self.log(f"  {batch_end:,} / {self.NUM_ORDERS:,} ({rate:,.0f} rec/sec, ETA: {eta:.0f}s)")
        
        insert_time = time.time() - start
        total_bytes += order_bytes
        self.results["metrics"]["order_insert_seconds"] = insert_time
        self.results["metrics"]["order_insert_rate"] = self.NUM_ORDERS / insert_time
        self.log(f"  Inserted in {insert_time:.1f}s ({self.NUM_ORDERS / insert_time:,.0f} rec/sec)")
        
        self.results["metrics"]["total_data_mb"] = total_bytes / 1024 / 1024
        self.log(f"Total data inserted: {total_bytes / 1024 / 1024:.1f} MB")
        
    def _get_entity_id(self, entity_name: str) -> str:
        """Get entity ID by name."""
        result = self.db.execute_sql(
            f"SELECT id FROM kdb_entity_definitions WHERE name = '{entity_name}' AND is_active = 1"
        )
        return result[0]["id"] if result else ""
    
    def test_queries(self):
        """Test various query operations."""
        self.log("Testing queries on JSONB storage...")
        
        # Get entity IDs
        order_id = self._get_entity_id("Order")
        customer_id = self._get_entity_id("Customer")
        
        # Count orders by status (JSONB query)
        start = time.time()
        result = self.db.execute_sql(
            f"SELECT COUNT(*) as cnt FROM kdb_records WHERE entity_id = '{order_id}' AND json_extract(data, '$.status') = 'delivered'"
        )
        query_time = time.time() - start
        count = result[0]["cnt"] if result else 0
        self.results["metrics"]["query_filter_seconds"] = query_time
        self.log(f"  Filter by status: {count:,} results in {query_time:.2f}s")
        
        # Count customers by tier (JSONB query)
        start = time.time()
        result = self.db.execute_sql(
            f"SELECT COUNT(*) as cnt FROM kdb_records WHERE entity_id = '{customer_id}' AND json_extract(data, '$.tier') = 'platinum'"
        )
        query_time = time.time() - start
        count = result[0]["cnt"] if result else 0
        self.results["metrics"]["query_tier_seconds"] = query_time
        self.log(f"  Filter by tier: {count:,} results in {query_time:.2f}s")
        
    def test_materialization(self):
        """Test materializing to dedicated tables."""
        self.log("Materializing entities to dedicated tables...")
        
        # Materialize customers
        start = time.time()
        self.db.materialize_entity("Customer")
        mat_time = time.time() - start
        self.results["metrics"]["customer_materialize_seconds"] = mat_time
        self.results["metrics"]["customer_materialize_rate"] = self.NUM_CUSTOMERS / mat_time
        self.log(f"  Customer: {mat_time:.1f}s ({self.NUM_CUSTOMERS / mat_time:,.0f} rec/sec)")
        
        # Materialize products
        start = time.time()
        self.db.materialize_entity("Product")
        mat_time = time.time() - start
        self.results["metrics"]["product_materialize_seconds"] = mat_time
        self.results["metrics"]["product_materialize_rate"] = self.NUM_PRODUCTS / mat_time
        self.log(f"  Product: {mat_time:.1f}s ({self.NUM_PRODUCTS / mat_time:,.0f} rec/sec)")
        
        # Materialize orders (the big one)
        start = time.time()
        self.db.materialize_entity("Order")
        mat_time = time.time() - start
        self.results["metrics"]["order_materialize_seconds"] = mat_time
        self.results["metrics"]["order_materialize_rate"] = self.NUM_ORDERS / mat_time
        self.log(f"  Order: {mat_time:.1f}s ({self.NUM_ORDERS / mat_time:,.0f} rec/sec)")
        
    def test_dedicated_queries(self):
        """Test queries on materialized tables."""
        self.log("Testing queries on dedicated tables...")
        
        # Query on dedicated Order table
        start = time.time()
        result = self.db.execute_sql(
            "SELECT COUNT(*) as cnt FROM kdb_order WHERE status = 'delivered'"
        )
        query_time = time.time() - start
        count = result[0]["cnt"] if result else 0
        self.results["metrics"]["dedicated_query_filter_seconds"] = query_time
        self.log(f"  Filter by status: {count:,} results in {query_time:.2f}s")
        
        # Query on dedicated Customer table
        start = time.time()
        result = self.db.execute_sql(
            "SELECT COUNT(*) as cnt FROM kdb_customer WHERE tier = 'platinum'"
        )
        query_time = time.time() - start
        count = result[0]["cnt"] if result else 0
        self.results["metrics"]["dedicated_query_tier_seconds"] = query_time
        self.log(f"  Filter by tier: {count:,} results in {query_time:.2f}s")
        
    def test_dematerialization(self):
        """Test dematerializing back to JSONB."""
        self.log("Dematerializing entities back to JSONB...")
        
        # Dematerialize orders (the big one first to free space)
        start = time.time()
        self.db.dematerialize_entity("Order")
        demat_time = time.time() - start
        self.results["metrics"]["order_dematerialize_seconds"] = demat_time
        self.results["metrics"]["order_dematerialize_rate"] = self.NUM_ORDERS / demat_time
        self.log(f"  Order: {demat_time:.1f}s ({self.NUM_ORDERS / demat_time:,.0f} rec/sec)")
        
        start = time.time()
        self.db.dematerialize_entity("Customer")
        demat_time = time.time() - start
        self.results["metrics"]["customer_dematerialize_seconds"] = demat_time
        self.log(f"  Customer: {demat_time:.1f}s ({self.NUM_CUSTOMERS / demat_time:,.0f} rec/sec)")
        
        start = time.time()
        self.db.dematerialize_entity("Product")
        demat_time = time.time() - start
        self.results["metrics"]["product_dematerialize_seconds"] = demat_time
        self.log(f"  Product: {demat_time:.1f}s ({self.NUM_PRODUCTS / demat_time:,.0f} rec/sec)")
        
    def verify_integrity(self):
        """Verify data integrity after all operations."""
        self.log("Verifying data integrity...")
        
        # Check counts using SQL with entity names from definitions
        result = self.db.execute_sql(
            """
            SELECT e.name, COUNT(*) as cnt 
            FROM kdb_records r 
            JOIN kdb_entity_definitions e ON r.entity_id = e.id 
            WHERE r.is_deleted = 0
            GROUP BY e.name
            """
        )
        counts = {r["name"]: r["cnt"] for r in result}
        
        customer_count = counts.get("Customer", 0)
        product_count = counts.get("Product", 0)
        order_count = counts.get("Order", 0)
        
        assert customer_count == self.NUM_CUSTOMERS, f"Customer count mismatch: {customer_count} != {self.NUM_CUSTOMERS}"
        assert product_count == self.NUM_PRODUCTS, f"Product count mismatch: {product_count} != {self.NUM_PRODUCTS}"
        assert order_count == self.NUM_ORDERS, f"Order count mismatch: {order_count} != {self.NUM_ORDERS}"
        
        self.log(f"  Customers: {customer_count:,} ✓")
        self.log(f"  Products: {product_count:,} ✓")
        self.log(f"  Orders: {order_count:,} ✓")
        self.results["metrics"]["integrity_verified"] = True
        
    def get_db_size(self) -> float:
        """Get database file size in MB."""
        if "sqlite" in self.db_url:
            db_path = self.db_url.replace("sqlite:///", "")
            if os.path.exists(db_path):
                return os.path.getsize(db_path) / 1024 / 1024
        return 0
        
    def cleanup(self):
        """Close database connection."""
        if self.db:
            db_size = self.get_db_size()
            if db_size > 0:
                self.results["metrics"]["db_file_size_mb"] = db_size
                self.log(f"Database file size: {db_size:.1f} MB")
            self.db.close()
            
    def run(self) -> dict:
        """Run the full stress test."""
        self.log("=" * 60)
        self.log(f"Starting 1GB Stress Test")
        self.log("=" * 60)
        
        overall_start = time.time()
        
        try:
            self.setup()
            self.insert_data()
            self.test_queries()
            self.test_materialization()
            self.test_dedicated_queries()
            self.test_dematerialization()
            self.verify_integrity()
            
            self.results["status"] = "success"
        except Exception as e:
            self.log(f"ERROR: {e}")
            self.results["status"] = "failed"
            self.results["error"] = str(e)
            raise
        finally:
            self.cleanup()
            
        total_time = time.time() - overall_start
        self.results["metrics"]["total_seconds"] = total_time
        
        self.log("=" * 60)
        self.log(f"Test completed in {total_time:.1f}s ({total_time / 60:.1f} min)")
        self.log("=" * 60)
        
        return self.results


def main():
    parser = argparse.ArgumentParser(description="KameleonDB 1GB Stress Test")
    parser.add_argument("--sqlite-only", action="store_true", help="Run SQLite test only")
    parser.add_argument("--postgres-only", action="store_true", help="Run PostgreSQL test only")
    parser.add_argument("--postgres-url", type=str, help="PostgreSQL connection URL")
    parser.add_argument("--sqlite-path", type=str, default="/tmp/kameleondb_stress_1gb.db",
                        help="SQLite database path")
    parser.add_argument("--both", action="store_true", help="Run both SQLite and PostgreSQL tests")
    args = parser.parse_args()
    
    results = []
    
    # Determine what to run
    run_sqlite = args.sqlite_only or args.both or (not args.postgres_only)
    run_postgres = args.postgres_only or args.both or (args.postgres_url and not args.sqlite_only)
    
    if run_sqlite:
        # Remove old SQLite file if exists
        if os.path.exists(args.sqlite_path):
            os.remove(args.sqlite_path)
            
        sqlite_url = f"sqlite:///{args.sqlite_path}"
        test = StressTest(sqlite_url, "SQLite")
        results.append(test.run())
        
    if run_postgres:
        if not args.postgres_url:
            print("ERROR: --postgres-url required for PostgreSQL test")
            sys.exit(1)
        test = StressTest(args.postgres_url, "PostgreSQL")
        results.append(test.run())
        
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for r in results:
        print(f"\n{r['label']}:")
        print(f"  Status: {r['status']}")
        if r['status'] == 'success':
            m = r['metrics']
            print(f"  Total Data: {m.get('total_data_mb', 0):.1f} MB")
            print(f"  Total Time: {m.get('total_seconds', 0):.1f}s")
            print(f"  Order Insert Rate: {m.get('order_insert_rate', 0):,.0f} rec/sec")
            print(f"  Order Materialize Rate: {m.get('order_materialize_rate', 0):,.0f} rec/sec")
            print(f"  Order Dematerialize Rate: {m.get('order_dematerialize_rate', 0):,.0f} rec/sec")
            if 'db_file_size_mb' in m:
                print(f"  DB File Size: {m['db_file_size_mb']:.1f} MB")
                
    # Save results to JSON
    results_path = "/tmp/kameleondb_stress_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to: {results_path}")


if __name__ == "__main__":
    main()
