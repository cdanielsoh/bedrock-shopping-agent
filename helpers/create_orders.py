import pandas as pd
import numpy as np

# Read input CSV files
users_df = pd.read_csv('data/personalize/users.csv')
items_df = pd.read_csv('data/personalize/items.csv')
interactions_df = pd.read_csv('data/personalize/interactions.csv')

# Filter for Purchase events
purchases = interactions_df[interactions_df['EVENT_TYPE'] == 'Purchase']

# Group purchases by user_id and timestamp to create orders
orders = purchases.groupby(['USER_ID', 'TIMESTAMP']).agg({
    'ITEM_ID': lambda x: x
}).reset_index()

orders = orders.sort_values(by='TIMESTAMP', ascending=True)
orders['TIMESTAMP'] = pd.to_datetime(orders['TIMESTAMP'], unit='s')

delivered_condition = orders['TIMESTAMP'] < '2020-08-17'
shipped_condition = (orders['TIMESTAMP'] >= '2020-08-17') & (orders['TIMESTAMP'] < '2020-08-20')

conditions = [
    delivered_condition,
    shipped_condition
]
choices = ['Delivered', 'Shipped']

# Create the new column using np.select
orders['DELIVERY_STATUS'] = np.select(conditions, choices, default='Processing')

# Add order_id as a unique identifier
orders['ORDER_ID'] = range(len(orders))

# Reorder columns to match required format
orders = orders[['ORDER_ID', 'USER_ID', 'TIMESTAMP', 'ITEM_ID', 'DELIVERY_STATUS']]

# Save to CSV
orders.to_csv('data/personalize/orders.csv', index=False)