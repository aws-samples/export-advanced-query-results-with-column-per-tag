#!/usr/bin/env python
# Script to export AWS Config advanced queries to CSV, but with tags as separate columns.

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import csv
import json
import boto3
import argparse
from botocore.config import Config

botoconfig=Config(retries={'max_attempts':10,'mode':'standard'})
config = boto3.client('config', config=botoconfig)

default_aggregator = "aws-controltower-GuardrailsComplianceAggregator"

# Get arguments:
parser = argparse.ArgumentParser(description='Generate a CSV file from a Config query.')
parser.add_argument('--query', type=str, help='The Config query to run.')
parser.add_argument('--aggregator', type=str, help='The name of the Config aggregator to run the query against.', default=default_aggregator)
parser.add_argument('--output', type=str, help='The name of the output CSV file.', default='results.csv')
parser.add_argument('--tags', type=str, help='A comma-separated list of tag keys that are required.')

args  = parser.parse_args()
aggregator_name = args.aggregator
output_filename = args.output
tags_required = args.tags.split(',') if args.tags else []
query = args.query
# If query wasn't specified, ask for it interactively:
if not query:
    print("Enter/Paste your Config query. Ctrl-D when done\n")
    contents = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        contents.append(line)
    query = ' '.join(contents)

print (f'Running query...')

# List of dicts representing the CSV:
final_results = []

# Run query:
paginator = config.get_paginator('select_aggregate_resource_config')

try:
    for page in paginator.paginate(Expression=query, ConfigurationAggregatorName=aggregator_name):
        results = page['Results']
        
        # If there is a SELECT on a nested object (like configuration.instanceType), select_aggregate_resource_config 
        # just returns the whole configuration object, and this separate "SelectFields" list that contains the 
        # dot notation fields that was in the SELECT, that the Config UI filters into a separate column.
        # We need to recreate that here. fields will contain something like ['accountId','configuration.InstanceType']
        # or whatever fields were selected:
        fields = page['QueryInfo']['SelectFields']
        fields = [item['Name'] for item in fields]        

        for result in results:
            # Result is a string of a JSON, convert it to a dict:
            result_dict = json.loads(result)

            # Process each field in order:
            for field in fields:
                # If the field is a nested object, split it into a list of keys:
                if '.' in field:
                    keys = field.split('.')
                    # Create a temp_dict to hold the nested object:
                    temp_dict = result_dict
                    # Loop through the keys, and assign the value to the temp_dict:
                    for key in keys:
                        temp_dict = temp_dict[key]
                    # Assign the value to the result_dict:
                    result_dict[field] = temp_dict

            # If the result_dict contains a "tags" key, read and remove it:
            if "tags" in result_dict:
                tags = result_dict.pop("tags")
                for tag in tags:
                    tag_key = tag["key"]
                    tag_value = tag["value"]

                    # If the tag_key already exists in the result_dict, print a warning:
                    if tag_key in result_dict:
                        print(f"WARNING: A resource has a Tag key that is the same name as one of the columns requested: {tag_key}")

                    # If tags_required was specified, check if the tag_key is in tags_required:
                    if tags_required and tag_key not in tags_required:
                        continue  # Skip this tag, it's not required.

                    # Add the tag to the result_dict:
                    result_dict[tag_key] = tag_value

            # If the result_dict contains a "accountId" key, modify the value to 
            # prepend "=" to force Excel to treat it as string
            # https://superuser.com/questions/318420/formatting-a-comma-delimited-csv-to-force-excel-to-interpret-value-as-a-string
            if "accountId" in result_dict:
                result_dict["accountId"] = f'="{result_dict["accountId"]}"'

            # Remove the nested fields original objects, eg. if we have configuration.instanceType, remove configuration from result_dict, but keep configuration.instanceType
            for field in fields:
                if '.' in field:
                    try:
                        result_dict.pop(field.split('.')[0])  # eg. remove configuration from result_dict, but keep configuration.instanceType
                    except:
                        pass

            # Add the result_dict to the csv_dict:
            final_results.append(result_dict)

except config.exceptions.InvalidExpressionException:
    print(f"Error: invalid Config SQL query: {query}")
    exit()

if not final_results:
    print("No results found.")
    exit()

with open( output_filename, 'w' ) as csv_file:
    writer = csv.writer( csv_file , quoting=csv.QUOTE_ALL)
    columns =  list({column for row in final_results for column in row.keys()})
    writer.writerow( columns )
    for row in final_results:
        writer.writerow([None if column not in row else row[column] for column in columns])

print(f'...query finished successfully. Go to the top right corner -> Actions -> Download file, and enter: {output_filename}')