import pandas as pd
import random
import os
import json

def trim_data(users_file='data/personalize/untrimmed/users.csv', 
              interactions_file='data/personalize/untrimmed/interactions.csv',
              items_file='data/personalize/untrimmed/items.csv',
              output_dir='data/personalize/trimmed'):
    """
    Sample 25 users from users.csv, then filter interactions and items data
    to include only data related to these sampled users.
    
    Args:
        users_file: Path to the users CSV file
        interactions_file: Path to the interactions CSV file
        items_file: Path to the items CSV file
        output_dir: Directory to save the trimmed data files
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Read the users data
    users_df = pd.read_csv(users_file)
    
    # Read the interactions data to find users with most interactions
    interactions_df = pd.read_csv(interactions_file)
    
    # Count interactions per user
    user_interaction_counts = interactions_df['USER_ID'].value_counts()
    
    # Get users with Purchase interactions
    purchase_interactions = interactions_df[interactions_df['EVENT_TYPE'] == 'Purchase']
    purchase_counts = purchase_interactions['USER_ID'].value_counts()
    
    # Start with top 25 users
    top_users = purchase_counts.head(25).index.tolist()
    total_purchases = purchase_counts.head(25).sum()
    
    # Add more users until we have >1000 purchases
    current_index = 25
    while total_purchases <= 1000 and current_index < len(purchase_counts):
        next_user = purchase_counts.index[current_index]
        top_users.append(next_user)
        total_purchases += purchase_counts.iloc[current_index]
        current_index += 1
    
    print(f"Selected {len(top_users)} users with {total_purchases} total purchases")
    
    # Filter users dataframe to include only these top users
    sampled_users = users_df[users_df['USER_ID'].isin(top_users)]
    
    # Read the interactions data
    interactions_df = pd.read_csv(interactions_file)
    
    # Filter interactions to include only the sampled users
    filtered_interactions = interactions_df[interactions_df['USER_ID'].isin(sampled_users['USER_ID'])]
    
    # Get the unique item IDs from the filtered interactions
    interaction_item_ids = filtered_interactions['ITEM_ID'].unique()
    
    # Read the items data
    items_df = pd.read_csv(items_file)
    
    # Filter items to include only those that appear in the filtered interactions
    filtered_items = items_df[items_df['ITEM_ID'].isin(interaction_item_ids)]
    
    # Save the trimmed datasets
    sampled_users.to_csv(f"{output_dir}/users.csv", index=False)
    filtered_interactions.to_csv(f"{output_dir}/interactions.csv", index=False)
    filtered_items.to_csv(f"{output_dir}/items.csv", index=False)
    
    print(f"Original users: {len(users_df)}, Sampled users: {len(sampled_users)}")
    print(f"Original interactions: {len(interactions_df)}, Filtered interactions: {len(filtered_interactions)}")
    print(f"Original items: {len(items_df)}, Filtered items: {len(filtered_items)}")
    
    return sampled_users, filtered_interactions, filtered_items


def trim_dynamodb_and_opensearch_data(sampled_users=None, filtered_items=None, 
                                     dynamodb_dir='data/dynamodb', 
                                     opensearch_dir='data/opensearch',
                                     output_dynamodb_dir='data/dynamodb/trimmed',
                                     output_opensearch_dir='data/opensearch/trimmed'):
    """
    Filter DynamoDB and OpenSearch data to include only data related to the sampled users and filtered items.
    
    Args:
        sampled_users: DataFrame containing the sampled users
        filtered_items: DataFrame containing the filtered items
        dynamodb_dir: Directory containing the DynamoDB data
        opensearch_dir: Directory containing the OpenSearch data
        output_dynamodb_dir: Directory to save the trimmed DynamoDB data
        output_opensearch_dir: Directory to save the trimmed OpenSearch data
    """
    # If sampled_users or filtered_items are not provided, load them from the trimmed files
    if sampled_users is None:
        sampled_users = pd.read_csv('data/personalize/trimmed/users.csv')
    
    if filtered_items is None:
        filtered_items = pd.read_csv('data/personalize/trimmed/items.csv')
    
    # Create output directories if they don't exist
    for directory in [output_dynamodb_dir, output_opensearch_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    # Get the list of user IDs and item IDs
    user_ids = sampled_users['USER_ID'].tolist()
    item_ids = filtered_items['ITEM_ID'].tolist()
    
    # Process DynamoDB data
    if os.path.exists(dynamodb_dir):
        dynamodb_files = [f for f in os.listdir(dynamodb_dir) if f.endswith('.json') or f.endswith('.csv')]
        
        for _file in dynamodb_files:
            file_path = os.path.join(dynamodb_dir, _file)
            output_file_path = os.path.join(output_dynamodb_dir, _file)
            
            if _file.endswith('.json'):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Filter data based on user_ids and item_ids
                # This is a simplified approach - adjust based on your actual data structure
                filtered_data = [item for item in data if 
                                ('id' in item and item['id'] in user_ids) or
                                ('id' in item and item['id'] in item_ids)]
                
                with open(output_file_path, 'w') as f:
                    json.dump(filtered_data, f, indent=2)
            
            elif _file.endswith('.csv'):
                df = pd.read_csv(file_path)
                
                # Filter data based on user_ids and item_ids
                if 'users' in _file:
                    filtered_df = df[df['id'].isin(user_ids)]
                elif 'items' in _file:
                    filtered_df = df[df['id'].isin(item_ids)]
                elif 'orders' in _file:
                    filtered_df = df[df['user_id'].isin(user_ids)]
                
                filtered_df.to_csv(output_file_path, index=False)   
    
    # Process OpenSearch data
    if os.path.exists(opensearch_dir):
        opensearch_files = [f for f in os.listdir(opensearch_dir) if f.endswith('.json') or f.endswith('.csv')]
        
        for file in opensearch_files:
            file_path = os.path.join(opensearch_dir, file)
            output_file_path = os.path.join(output_opensearch_dir, file)
            
            if file.endswith('.json'):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Filter data based on user_ids and item_ids
                # This is a simplified approach - adjust based on your actual data structure
                filtered_data = [item for item in data if 
                                ('id' in item and item['id'] in item_ids)]
                
                with open(output_file_path, 'w') as f:
                    json.dump(filtered_data, f, indent=2)
            
            elif _file.endswith('.csv'):
                df = pd.read_csv(file_path)
                
                filtered_df = df[df['id'].isin(item_ids)]
                
                filtered_df.to_csv(output_file_path, index=False)
    
    print(f"Trimmed DynamoDB and OpenSearch data saved to {output_dynamodb_dir} and {output_opensearch_dir}")


if __name__ == "__main__":
    trim_data()
    trim_dynamodb_and_opensearch_data()