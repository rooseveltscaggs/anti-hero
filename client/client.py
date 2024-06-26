import multiprocessing as mp
from multiprocessing import Process
import datetime
import requests
import time
import csv
import random
import re
import os

ORC_URL = ""
ORC_IP = ""
ORC_PORT = ""
SERVER_MAP = {}
INVENTORY_MAP = {}
EXPERIMENT_ARGS_LEN = 13

def range_to_list(range_string):
    items = []
    range_list = range_string.split(",")
    for entry in range_list:
        # create a list that is range and add to items array
        if "-" in entry:
            range_arr = entry.split("-")
            begin = int(range_arr[0])
            end = int(range_arr[1])
            for i in range(begin, end+1):
                items.append(i)
        else:
            # add single number to items
            items.append(int(entry))
    return items

def get_orchestrator():
    global ORC_IP
    global ORC_PORT
    global ORC_URL
    print("Default Orchestrator URL: 10.10.1.1:8000")
    ORC_IP = input("Enter the IP Address of the Orchestrator (Press ENTER for default): ") or "10.10.1.1"
    ORC_PORT = input("Enter the port number of the Orchestrator (Press ENTER for default): ") or "8000"
    ORC_URL = f'http://{ORC_IP}:{ORC_PORT}'
    return ORC_URL

def print_servers():
    for server in SERVER_MAP.values():
        server_summary = f'{server["id"]}) {server["hostname"]} - Last seen: {server["last_updated"]}'
        print(server_summary)

def download_server_map():
    # Download servers from orchestrator (Success!)
    print("Downloading server map from Orchestrator...")
    servers_url = f'{ORC_URL}/servers'
    servers_resp = requests.get(servers_url)
    if servers_resp.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        global SERVER_MAP
        json_obj = servers_resp.json()
        for item in json_obj:
            SERVER_MAP[item['id']] = item
        print('\nServer List by ID:')
        for server in SERVER_MAP.values():
            server_summary = f'{server["id"]}) {server["hostname"]} - Last seen: {server["last_updated"]} - Partner: {server["partner_id"]}'
            print(server_summary)


def register_new_server():
    host = input("Enter the IP Address of the new server: ")
    port = input("Enter the port number of the new server: ")
    server_url = f'http://{host}:{port}'
    # Send Orchestrator details to server
    orc_update_slug = f'/orchestrator?ip_address={ORC_IP}&port={ORC_PORT}'
    update_url = server_url + orc_update_slug
    print("Sending Orchestrator's location to server")
    requests.request("PUT", update_url)
    # Send autoregister request to server
    orc_autoreg_slug = f'/orchestrator/register?port={port}'
    autoreg_url = server_url + orc_autoreg_slug
    print("Instructing server to automatically register with Orchestrator...")
    requests.request("POST", autoreg_url)
    download_server_map()

def main_menu():
    print("\n-- Client Options --")
    # Complete
    print("1) Re-Download Server Map")
    # In Progress
    print("2) Register New Server")
    print("3) Transfer Inventory")
    print("4) Sync Inventory")
    print("5) Re-Download Inventory Map")
    print("6) Pair Servers")
    print("7) Enable Server")
    print("8) Disable Server")
    print("9) View/Search Inventory")
    print("10) Send Automated Requests (Simple)")
    print("11) Simple Experiment Configurator")
    print("12) Test Inventory")
    print("13) Buy Inventory")
    print("RESET) Reset All Servers")
    print("\n")
    return input("Enter the number of an option above: ")

def make_request():
    url = input("Enter the URL: ")
    method = input("Enter the HTTP method (GET or POST): ").upper()

    if method not in ['GET', 'POST']:
        print("Invalid method. Please enter GET or POST.")
        return

    if method == 'GET':
        try:
            response = requests.get(url)
            response.raise_for_status()
            print(f"Response: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
    else:
        data = input("Enter the data to send (if any): ")
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
            print(f"Response: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")

def transfer_inventory():
    ids = []
    range_string = input("Enter an inclusive range of inventory ids (e.g.: \"1-8, 11, 17\"): ")
    range_list = range_string.split(",")
    for entry in range_list:
        # create a list that is range and add to ids
        if "-" in entry:
            range_arr = entry.split("-")
            begin = int(range_arr[0])
            end = int(range_arr[1])
            for i in range(begin, end+1):
                ids.append(i)
        else:
            # add single number to ids
            ids.append(int(entry))
    print(ids[0:5])
    print(ids[len(ids)-5:])
    print(len(ids))
    print_servers()
    server_id = input("Choose a server to transfer inventory to: ")

    print("Sending transfer request to Orchestrator...")
    # send ids array to orchestrator
    transfer_url = f'http://{ORC_IP}:{ORC_PORT}/inventory/transfer?destination={server_id}'
    response = requests.request("PUT", transfer_url, headers={}, json = ids)

    if response.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        # json_data = response.json()
        print("Request sent... waiting for changes to propagate")
        time.sleep(3)
        # sync_servers()
        # update_inventory_map()
    else:
        print("Bad response from Orchestrator")

def sync_servers(wait=True):
    if wait:
        print("Auto-Sync: Waiting for previous changes to propagate...")
        time.sleep(3)
    print("Sending sync request to Orchestrator...")
    curr_url = f'http://{ORC_IP}:{ORC_PORT}/servers/sync'
    response = requests.request("PUT", curr_url)
    print("Request sent!")

def download_inventory_map(inv_id=None):
    global INVENTORY_MAP
    # Download servers from orchestrator (Success!)
    if inv_id:
        # Silently update 
        servers_url = f'{ORC_URL}/inventory/{inv_id}'
        servers_resp = requests.get(servers_url)
        if servers_resp.ok:
            # If the response status code is 200 (OK), parse the response as JSON
            json_obj = servers_resp.json()
            INVENTORY_MAP[int(inv_id)] = json_obj
        return
    
    if len(INVENTORY_MAP) > 1000:
        continue_download = input("Large download: continue inventory refresh? (y/n): ")
        if continue_download.lower() != "y":
            return
                
    print("Downloading inventory map from Orchestrator...")
    servers_url = f'{ORC_URL}/inventory'
    servers_resp = requests.get(servers_url)
    if servers_resp.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        # global INVENTORY_MAP
        json_obj = servers_resp.json()
        for item in json_obj:
            INVENTORY_MAP[item['id']] = item

def pair_servers():
    print_servers()
    server1 = input("Choose the first server to pair: ")
    server2 = input("Choose the second server to pair: ")

    pair_url = f'{ORC_URL}/pair?server1_id={server1}&server2_id={server2}'
    response = requests.request("PUT", pair_url)
    if response.ok:
        print("Request sent... waiting for changes to propagate")
        time.sleep(3)
        download_server_map()
    else:
        print("Error sending request...")

def enable_server():
    print_servers()
    server_id = int(input("Choose server to enable: "))
    server = SERVER_MAP[server_id]
    enable_url = f'http://{server["ip_address"]}:{server["port"]}/enable'
    response = requests.request("PUT", enable_url)
    if response.ok:
        print("Enable request sent!")
    else:
        print("Error sending request")

def disable_server():
    print_servers()
    server_id = int(input("Choose server to disable: "))
    server = SERVER_MAP[server_id]
    disable_url = f'http://{server["ip_address"]}:{server["port"]}/disable'
    response = requests.request("PUT", disable_url)
    if response.ok:
        print("Disable request sent!")
    else:
        print("Error sending request")

def view_search_inventory():
    global INVENTORY_MAP
    download_inventory_map()
    print('\n-- Inventory Preview --')
    preview_max = max(0, len(INVENTORY_MAP))
    preview_min = min(preview_max, 5)
    # Print the first 5 key-value pairs
    for _, seat in list(INVENTORY_MAP.items())[:preview_min]:
        inv_summary = f'Seat ID {seat["id"]}) Section {seat["section"]} Row {seat["row"]} Seat {seat["seat"]} - Location: {seat["location"]} - Status: {seat["availability"]}'
        print(inv_summary)
    while True:
        seat_id = input("Enter an inventory id for details or type q to quit: ")
        if seat_id == "q":
            break
        download_inventory_map(seat_id)
        seat = INVENTORY_MAP[int(seat_id)]
        inv_summary = f'Seat ID {seat["id"]}) Section {seat["section"]} Row {seat["row"]} Seat {seat["seat"]} - Location: {seat["location"]} - Status: {seat["availability"]}'
        print(inv_summary)

def test_inventory():
    global SERVER_MAP
    print_servers()
    server_id = int(input("Choose the server to test: "))
    inv_id = input("Enter an inventory id to test: ")

    server = SERVER_MAP[server_id]
    servers_url = f'http://{server["ip_address"]}:{server["port"]}/inventory/{inv_id}'
    server_resp = requests.get(servers_url)
    if server_resp.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        print("--- Request Successful ---")
        json_obj = server_resp.json()
        print(json_obj)
    else:
        print("--- Request Failure ---")
        print(server_resp)
    return


def buy_inventory():
    global SERVER_MAP
    global INVENTORY_MAP
    print("* Inventory Purchased must be located in same server pod *")
    inv_range_string = input("Enter an inventory range to buy: ")
    inv_range = range_to_list(inv_range_string)
    # server_id = int(input("Choose the server to test: "))

    # Check first ID to see where it is located
    inventory = INVENTORY_MAP[int(inv_range[0])]
    primary_server = SERVER_MAP[int(inventory["location"])]
    backup_server = SERVER_MAP[int(inventory["location"])]
    if primary_server["partner_id"]:
        backup_server = SERVER_MAP[int(primary_server["partner_id"])]
    
    primary_url = f'http://{primary_server["ip_address"]}:{primary_server["port"]}/inventory/buy/reserve'
    backup_url = f'http://{backup_server["ip_address"]}:{backup_server["port"]}/inventory/buy/reserve'
    
    # server_resp = requests.get(servers_url)
    # curr_url = f'http://{partner.ip_address}:{partner.port}/inventory/forward'

    successful_server = None

    while True:
        try:
            response = requests.request("POST", primary_url, json=inv_range, timeout=3)
            if response.ok:
                successful_server = primary_server
                break
        except requests.exceptions.HTTPError as errh:
            print ("Http Error:",errh)
        except requests.exceptions.ConnectionError as errc:
            print ("Error Connecting:",errc)
        except requests.exceptions.Timeout as errt:
            print ("Timeout Error:",errt)
        except requests.exceptions.RequestException as err:
            print ("Oops: Something Else",err)

        try:
            response = requests.request("POST", backup_url, json=inv_range, timeout=3)
            if response.ok:
                successful_server = backup_server
                break
        except requests.exceptions.HTTPError as errh:
            print ("Http Error:",errh)
        except requests.exceptions.ConnectionError as errc:
            print ("Error Connecting:",errc)
        except requests.exceptions.Timeout as errt:
            print ("Timeout Error:",errt)
        except requests.exceptions.RequestException as err:
            print ("Oops: Something Else",err)

        
    if response.ok:
        json_obj = response.json()
        transaction_id = json_obj["transaction_id"]
        reserved_ids = json_obj["reserved_ids"]
        # If the response status code is 200 (OK), parse the response as JSON
        print(f'Transaction ID: {transaction_id} -- {len(reserved_ids)} ids reserved')
        input("Reserve Request Successful... press ENTER to send payment details")

        payment_url = f'http://{successful_server["ip_address"]}:{successful_server["port"]}/inventory/buy/payment'
        
        payment_details = {
            "credit_card_number": ''.join([str(random.randint(0, 9)) for _ in range(16)]),
            "transaction_id": transaction_id,
        }

        while True:
            try:
                response = requests.request("POST", payment_url, json=payment_details, timeout=3)
                if response.ok:
                    break
            except requests.exceptions.HTTPError as errh:
                print ("Http Error:",errh)
            except requests.exceptions.ConnectionError as errc:
                print ("Error Connecting:",errc)
            except requests.exceptions.Timeout as errt:
                print ("Timeout Error:",errt)
            except requests.exceptions.RequestException as err:
                print ("Oops: Something Else",err)
            input("Payment Processing Failed: Press ENTER to try again")
        print("Purchase Completed!")
        print(response.json())


    else:
        print("--- Request Failure ---")
        print(response)
    return

def simple_experiment_configurator():
    config_string = ""
    # Experiment Name
    experiment_name = input("Enter a name for this experiment: ")
    exp_name_clean = experiment_name.replace(" ", "_")
    config_string += exp_name_clean

    # Request Delay
    delay = input("\nEnter a delay time between requests (in seconds): ")
    config_string += ("|" + delay)

    # Server ID
    print_servers()
    server_id = input("\nEnter a server ID for requests to be sent to: ")
    config_string += ("|" + server_id)

    # Endpoint Options
    print("\n---- Endpoint Options ----")
    print("1) Latency Test")
    print("2) Inventory View (Read Only)")
    print("3) Inventory Buy (Attempt to Reserve)")
    endpoint = input("\nEnter an option above: ")
    config_string += ("|" + endpoint)
   
    # Inventory Range to Request
    range_string = input("Enter an inclusive range of inventory ids (e.g.: \"1-8, 11, 17\"): ")
    config_string += ("|" + range_string)

    print("\n---- Start Time Options ----")
    print("Text entered can be relative (h, m, s) or absolute (UTC)")
    print("Examples: 10m, 10s, 2023-12-05T01:45:00")
    print(f"Current Datetime (UTC): {datetime.datetime.utcnow().isoformat()}")
    start_time_string = input("Enter a start time for the experiment: ") or "1m"
    last_char = (start_time_string[len(start_time_string)-1:len(start_time_string)]).lower()
    start_time_interval = start_time_string[:len(start_time_string)-1]

    match last_char:
            case "s":
                start_time_value = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(start_time_interval))

            case "m":
                start_time_value = datetime.datetime.utcnow() + datetime.timedelta(minutes=int(start_time_interval))

            case "h":
                start_time_value = datetime.datetime.utcnow() + datetime.timedelta(hours=int(start_time_interval))

            case _:
                start_time_value = datetime.datetime.fromisoformat(start_time_string)
    
    config_string += ("|" + start_time_value.isoformat()[:19])

    print("\n---- End Time Options ----")
    print("Text entered can be relative to start time (h, m, s) or absolute (UTC)")
    print("Examples: 10m, 10s, 2023-12-05T01:45:00")
    print(f"Current Datetime (UTC): {datetime.datetime.utcnow().isoformat()}")
    end_time_string = input("Enter an end time for the experiment: ") or "1m"
    last_char = (end_time_string[len(end_time_string)-1:len(end_time_string)]).lower()
    end_time_interval = end_time_string[:len(end_time_string)-1]

    match last_char:
            case "s":
                end_time_value = start_time_value + datetime.timedelta(seconds=int(end_time_interval))

            case "m":
                end_time_value = start_time_value + datetime.timedelta(minutes=int(end_time_interval))

            case "h":
                end_time_value = start_time_value + datetime.timedelta(hours=int(end_time_interval))

            case _:
                end_time_value = datetime.datetime.fromisoformat(start_time_string)
    
    config_string += ("|" + end_time_value.isoformat()[:19])

    # Inventory Range to Request
    print(f'Max. number of workers is {int(mp.cpu_count())}')
    worker_count = input("Enter number of parallel workers to run: ")
    config_string += ("|" + worker_count)

    # Inventory Range to Request
    contact_backup = input("Contact backup on bad response? (y/n): ")
    config_string += ("|" + contact_backup)
    
    delay_decrease_string = input("Amount of second to decrease delay every 10 iterations: ")
    config_string += ("|" + str(float(delay_decrease_string or 0)))

    print("\nGenerated config string: ")
    print(str("\n" + config_string))

    run_now = input("Run this config now? (y/n) ")
    if run_now.lower() == "y":
        simple_experiment(config_string)


# retry_count = -1, 0, 1+
# If count == 0, continue to next request
# def send_and_record(filepath, start_time, stop_time, url1, url2, 
#                     initial_delay, inv_array, initial_try_count,  
#                     descriptor="None"):
#     with open(filepath, 'w', newline='') as csvfile:
#         csv_writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
#         csv_writer.writerow(['Request Sent', 'Response Received', 'Response', 'Descriptor'])

#         print("Waiting for experiment start time...")
#         while start_time > datetime.datetime.utcnow():
#             time.sleep(1)

#         urls = [url1, url2]
#         url_index = 0
#         # Set initial delay
#         curr_delay = 25
#         i = 0

        

#         # WHILE
#         # If request_delay_option is 1 and i >= 100: decrease curr_delay by 5 seconds (until 0)
#         # 

#         # Choose inventory ID from range array (random or linear)
#         inv_id = random.choice(inv_array)
#         # Build URL (based on endpoint + inventory ID)
#         curr_url = urls[url_index] + "/" + str(inv_id)

#         # Send request
#         try_count = initial_try_count 
#         while try_count != 0 and :
#             try:
#                 request_datetime = str(datetime.datetime.utcnow())
#                 response = requests.get(curr_url)
#                 response_datetime = str(datetime.datetime.utcnow())
#                 if response.ok:
#                     csv_writer.writerow([request_datetime, response_datetime, 'Success', descriptor])
#                 else:
#                     csv_writer.writerow([request_datetime, response_datetime, 'Failure', descriptor])
#             except requests.exceptions.RequestException as e:
#                 # print(f"Error: {e}")
#                 csv_writer.writerow([request_datetime, "N/A", 'Failure', descriptor])
#             try_count -= 1

#         # Log result
#         # If failed, follow procedure (ignore and continue, try again indefinitely, try again X number of time)
#             # Still failing? Switch to Backup
#         # If successful, start loop over with primary




#         while stop_time > datetime.datetime.utcnow():
#             current_datetime = str(datetime.datetime.utcnow())


#             try:
#                 response = requests.get(url)
#                 response_datetime = str(datetime.datetime.utcnow())
#                 if response.ok:
#                     csv_writer.writerow([current_datetime, 'Success', descriptor])
#                 else:
#                     csv_writer.writerow([current_datetime, 'Failure', descriptor])
#             except requests.exceptions.RequestException as e:
#                 # print(f"Error: {e}")
#                 csv_writer.writerow([current_datetime, 'Failure', descriptor])

            
#     return

# retry_count = -1, 0, 1+
# If count == 0, continue to next request
def simple_requests(filepath, start_time, stop_time, server_url, 
                    backup_url, delay, inv_array, descriptor="None", delay_decrease_factor=0):
    with open(filepath, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(['Request Sent', 'Response Received', 'Response', 'Order', 'Endpoint', 'InventoryID', 'Descriptor'])
        can_request_backup = False
        if backup_url is not None:
            can_request_backup = True

        shuffled_array = inv_array.copy()
        random.shuffle(shuffled_array)
        curr_delay = delay

        print("Waiting for experiment start time...")
        while start_time > datetime.datetime.utcnow():
            time.sleep(1)

        print("Beginning experiment...")
        i = 0
        while stop_time > datetime.datetime.utcnow() and i < len(shuffled_array):
            bad_resp = False
            # -1: no backup, 0: no backup, 1: backup
            # Choose inventory ID from range array (random or linear)
            # inv_id = random.choice(inv_array)
            inv_id = shuffled_array[i]
            # Send request
            try:
                # Build URL (based on endpoint + inventory ID)
                if "/buy/reserve" in server_url:
                    curr_url = server_url
                    request_datetime = str(datetime.datetime.utcnow())
                    # response = requests.post(curr_url, timeout=3)
                    response = requests.request("POST", curr_url, json=[inv_id], timeout=3)
                    response_datetime = str(datetime.datetime.utcnow())
                else:
                    curr_url = server_url + "/" + str(inv_id)
                    request_datetime = str(datetime.datetime.utcnow())
                    response = requests.get(curr_url, timeout=3)
                    response_datetime = str(datetime.datetime.utcnow())
                if response.ok:
                    csv_writer.writerow([request_datetime, response_datetime, 'Success', 'Primary', curr_url, inv_id, descriptor])
                else:
                    csv_writer.writerow([request_datetime, response_datetime, 'Failure', 'Primary', curr_url, inv_id, response.status_code])
                    bad_resp = True
            except requests.exceptions.RequestException as e:
                # print(f"Error: {e}")
                csv_writer.writerow([request_datetime, "N/A", 'Failure', 'Primary', curr_url, inv_id, e])
                bad_resp = True
            
            if bad_resp and can_request_backup:
                # send request to backup and record
                try:
                    if "/buy/reserve" in backup_url:
                        curr_url = backup_url
                        request_datetime = str(datetime.datetime.utcnow())
                        # response = requests.post(curr_url, timeout=3)
                        response = requests.request("POST", curr_url, json=[inv_id], timeout=3)
                        response_datetime = str(datetime.datetime.utcnow())
                    else:
                        curr_url = backup_url + "/" + str(inv_id)
                        request_datetime = str(datetime.datetime.utcnow())
                        response = requests.get(curr_url, timeout=3)
                        response_datetime = str(datetime.datetime.utcnow())
                    if response.ok:
                        csv_writer.writerow([request_datetime, response_datetime, 'Success', 'Backup', curr_url, inv_id, descriptor])
                    else:
                        csv_writer.writerow([request_datetime, response_datetime, 'Failure', 'Backup', curr_url, inv_id, response.status_code])
                except requests.exceptions.RequestException as e:
                    # print(f"Error: {e}")
                    csv_writer.writerow([request_datetime, "N/A", 'Failure', 'Backup', curr_url, inv_id, e])
            i += 1
            if (i % 10 == 0):
                curr_delay = max(0, curr_delay-delay_decrease_factor)
            time.sleep(curr_delay)



def simple_experiment(config_string=""):
    config_arr = config_string.split("|")
    while True:
        if len(config_arr) != 10:
            config_string = input("Enter the configuration string for this experiment: ")
            config_arr = config_string.split("|")
        if len(config_arr) == 10:
            break
        else:
            print("Invalid configuration string: wrong number of args")
    
    SLUGS_ARR = ['/latency', '/inventory', '/inventory/buy/reserve']

    experiment_name = config_arr[0]

    delay = float(config_arr[1])
    endpoint_slug = SLUGS_ARR[int(config_arr[3])-1]

    server = SERVER_MAP[int(config_arr[2])]
    server_url = f'http://{server["ip_address"]}:{server["port"]}{endpoint_slug}'

    if server.get("partner_id", None) and config_arr[8].lower() == 'y':
        backup = SERVER_MAP[server["partner_id"]]
        backup_url = f'http://{backup["ip_address"]}:{backup["port"]}{endpoint_slug}'
    else:
        backup_url = None
    

    inv_range_string  = config_arr[4]
    inv_arr = range_to_list(inv_range_string)

    start_time = datetime.datetime.fromisoformat(config_arr[5])
    stop_time = datetime.datetime.fromisoformat(config_arr[6])

    delay_decrease = float(config_arr[9] or 0)
    
    os.makedirs("experiments/" + experiment_name)

    worker_count = int(config_arr[7])
    num_workers = min(int(mp.cpu_count()), worker_count)
    for i in range(1, num_workers+1):
        filepath = "experiments/" + experiment_name + "/" + f'{experiment_name[:12]}_worker_{i}.csv'
        process = Process(target=simple_requests, args=(filepath, start_time, stop_time, server_url, backup_url, delay, inv_arr, "None", delay_decrease))
        process.start()
        if i == num_workers:
            print("Workers started, running experiment...")
            process.join()
    print("Experiment complete!")


def send_requests():
    while True:
        config_string = input("Enter the configuration string for this experiment: ")
        config_arr = config_string.split("|")
        if len(config_arr) == EXPERIMENT_ARGS_LEN:
            break
        else:
            print("Invalid configuration string: wrong number of args")
    
    SLUGS_ARR = ['/latency', '/inventory', '/inventory/buy']

    experiment_name = config_arr[0]
    endpoint_index = int(config_arr[1]) - 1
    request_delay_option = int(config_arr[2])
    delay_spec = int(config_arr[3])
    inventory_range_option = int(config_arr[4])

    # Needs to be altered
    range_spec_string = config_arr[5]
    range_arr = range_to_list(range_spec_string)

    server_contact_option = int(config_arr[6])
    loop_count = int(config_arr[7])
    request_failure_procedure = int(config_arr[8])
    retry_spec = int(config_arr[9])
    start_time = datetime.datetime.fromisoformat(config_arr[10])
    stop_time = datetime.datetime.fromisoformat(config_arr[11])
    num_workers = int(config_arr[12])
    

    endpoint_slug = SLUGS_ARR[endpoint_index]

    for i in range(1, num_workers+1):
        process = Process(target=send_and_record, args=(f"primary_{stop_time}_worker_{i}.csv", primary_url, start_time, stop_time, "Primary",))
        process.start()
        if i == (num_workers - 1) :
            print("Running experiment...")
            process.join()



    


def reset_all_servers():
    global SERVER_MAP
    download_server_map()
    print("Sending inventory reset command to all servers...")
    for server in SERVER_MAP.values():
        server_url = f'http://{server["ip_address"]}:{server["port"]}/reset'
        requests.request("PUT", server_url)
    
    orc_reset_url = f'http://{ORC_IP}:{ORC_PORT}/reset'
    requests.request("PUT", orc_reset_url)
    print("Request(s) sent!")

if __name__ == "__main__":
    while True:
        # Ask for Orchestrator IP and Port
        ORC_URL = get_orchestrator()

        # Attempt to connect to Orchestrator
        status_url = f'{ORC_URL}/status'
        status_resp = requests.get(status_url)
        if status_resp.ok:
            print("\nSuccessfully connected to Orchestrator!")
            download_server_map()
            download_inventory_map()
            break
        else:
            print("\nError connecting to Orchestrator...")
    
    while True:
        option = main_menu()
        # Choose request mode: continuous or set number of requests
        # Enter start date/time (UTC)
        # Choose inventory to request: Random, Choose by Location, Choose by Section, Choose by Desirability
        
        match option:
            case "1":
                download_server_map()

            case "2":
                register_new_server()

            case "3":
                transfer_inventory()

            case "4":
                sync_servers(wait=False)

            case "5":
                download_inventory_map()

            case "6":
                pair_servers()

            case "7":
                enable_server()
            
            case "8":
                disable_server()
            
            case "9":
                view_search_inventory()
            
            case "10":
                simple_experiment()

            case "11":
                simple_experiment_configurator()
            
            case "12":
                test_inventory()

            case "13":
                buy_inventory()
            
            case "RESET":
                reset_all_servers()

            case "debug":
                print("--- DEBUG ---")
                print(INVENTORY_MAP)
            
            case _:
                print("Error: Selection did not match any options")
        
        # Recoverable

        # try:
        #     match option:
        #         case "1":
        #             download_server_map()

        #         case "2":
        #             register_new_server()

        #         case "3":
        #             transfer_inventory()

        #         case "4":
        #             sync_inventory()

        #         case "5":
        #             download_inventory_map()

        #         case "6":
        #             pair_servers()

        #         case "7":
        #             enable_server()
                
        #         case "8":
        #             disable_server()
                
        #         case "9":
        #             view_search_inventory()
                
        #         case "10":
        #             send_requests()
                
        #         case _:
        #             print("Error: Selection did not match any options")
        # except Exception as error:
        #     print("An exception occurred:", error) 
        input("\nPress Enter to Continue...")