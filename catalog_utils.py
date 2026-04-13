from catalog_data import GFS_CATALOG_TREE

def get_url(department, sub_category=None, leaf_category=None):
    """
    Surgical URL retrieval.
    Example: get_url("Beef", "Steak", "New York Strip")
    """
    try:
        dept = GFS_CATALOG_TREE.get(department)
        if not dept: return None
        
        # If only department is provided, return all L2 URLs in it
        if not sub_category:
            return [node["url"] for node in dept["nodes"].values()]

        node = dept["nodes"].get(sub_category)
        if not node: return None

        # If no leaf is provided, return the L2 node URL
        if not leaf_category:
            return node["url"]

        # Return the specific L3 leaf URL
        return node["leaves"].get(leaf_category)
    except Exception:
        return None

def find_path_by_url(target_url):
    """
    Reverse lookup: Give it a URL, it tells you the breadcrumb path.
    Useful for the bot to identify its location if it gets lost.
    """
    for dept_name, dept_data in GFS_CATALOG_TREE.items():
        for node_name, node_data in dept_data["nodes"].items():
            if node_data["url"] == target_url:
                return f"Categories > {dept_name} > {node_name}"
            for leaf_name, leaf_url in node_data["leaves"].items():
                if leaf_url == target_url:
                    return f"Categories > {dept_name} > {node_name} > {leaf_name}"
    return "Unknown Path"

def get_all_harvest_urls():
    """
    Returns a flat list of every single Level 3 URL in the system.
    Use this to tell the bot to 'Scrape Everything' sequentially.
    """
    all_urls = []
    for dept in GFS_CATALOG_TREE.values():
        for node in dept["nodes"].values():
            all_urls.extend(node["leaves"].values())
    return all_urls

def flatten_for_excel():
    """
    Converts the nested table tree into a flat list of rows.
    Perfect for passing to openpyxl to build your Master Catalog.
    """
    rows = []
    for dept_name, dept_data in GFS_CATALOG_TREE.items():
        for node_name, node_data in dept_data["nodes"].items():
            # Add the Sub-Category (Node) level first
            rows.append({
                "Level 1": dept_name,
                "Level 2": node_name,
                "Level 3": "",
                "URL": node_data["url"]
            })
            # Add all Sub-Sub-Categories (Leaves)
            for leaf_name, leaf_url in node_data["leaves"].items():
                rows.append({
                    "Level 1": dept_name,
                    "Level 2": node_name,
                    "Level 3": leaf_name,
                    "URL": leaf_url
                })
    return rows

# --- Quick Diagnostic Test ---
if __name__ == "__main__":
    print("🔍 Testing Catalog Brain...")
    
    # Test 1: Drill down
    test_url = get_url("Beef", "Steak", "New York Strip")
    print(f"✅ URL for New York Strip: {test_url}")
    
    # Test 2: Reverse Lookup
    path = find_path_by_url("https://order.gfs.com/categories/results/3~075")
    print(f"✅ Path for 3~075: {path}")
    
    # Test 3: Total Count
    all_targets = get_all_harvest_urls()
    print(f"✅ Total harvestable nodes found: {len(all_targets)}")