import multiprocessing as mp
from multiprocessing import Process
import datetime
import requests
import time
import csv

ORC_URL = ""
ORC_IP = ""
ORC_PORT = ""
SERVER_MAP = {}
INVENTORY_MAP = {}

def get_orchestrator():
    global ORC_IP
    global ORC_PORT
    global ORC_URL
    ORC_IP = input("Enter the IP Address of the Orchestrator: ")
    ORC_PORT = input("Enter the port number of the Orchestrator: ")
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
    requests.request("PUT", update_url)
    # Send autoregister request to server
    orc_autoreg_slug = f'/orchestrator/register?port={port}'
    autoreg_url = server_url + orc_autoreg_slug
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
    print("10) Send Automated Requests")
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
        time.sleep(5)
        # update_inventory_map()
    else:
        print("Bad response from Orchestrator")

def sync_servers():
    print("Sending sync request to Orchestrator...")
    curr_url = f'http://{ORC_IP}:{ORC_PORT}/servers/sync'
    response = requests.request("PUT", curr_url)
    print("Request sent!")

def download_inventory_map():
    # Download servers from orchestrator (Success!)
    print("Downloading inventory map from Orchestrator...")
    servers_url = f'{ORC_URL}/inventory'
    servers_resp = requests.get(servers_url)
    if servers_resp.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        global INVENTORY_MAP
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
    download_inventory_map()
    print('\n-- Inventory Preview --')
    preview_max = max(0, len(INVENTORY_MAP))
    preview_min = min(preview_max, 5)
    # Print the first 5 key-value pairs
    for _, seat in list(INVENTORY_MAP.items())[:preview_min]:
        inv_summary = f'Seat ID {seat["id"]}) Section {seat["section"]} Row {seat["row"]} Seat {seat["seat"]} - Location: {seat["location"]} - Status: {seat["availability"]}'
        print(inv_summary)
    while True:
        seat_id = input("Enter an inventory id for details: ")
        seat = INVENTORY_MAP[int(seat_id)]
        inv_summary = f'Section {seat["section"]}) Row {seat["row"]} Seat {seat["seat"]} - Location: {seat["location"]} - Status: {seat["availability"]}'
        print(inv_summary)
        exit = input("Press ENTER to continue searching or type q to quit: ")
        if exit == "q":
            break

def send_and_record(filename, url, start_time, stop_time, descriptor="None"):
    with open(filename, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(['Timestamp', 'Response', 'Descriptor'])
        while start_time > datetime.datetime.utcnow():
            time.sleep(1)
        while stop_time > datetime.datetime.utcnow():
            current_datetime = str(datetime.datetime.utcnow())
            try:
                response = requests.get(url)
                if response.ok:
                    csv_writer.writerow([current_datetime, 'Success', descriptor])
                else:
                    csv_writer.writerow([current_datetime, 'Failure', descriptor])
            except requests.exceptions.RequestException as e:
                # print(f"Error: {e}")
                csv_writer.writerow([current_datetime, 'Failure', descriptor])
    return

def send_requests():
    # Continuous, Timed/Scheduled,
    # Static, Random (Unbounded), Random (Bounded)
    # Inject Failure at time t = ?
    # first_success = False
    # request_count = 0

    # wait_time = int(input("Enter a wait time (seconds) between requests: ") or 0)
    inv_id = input("Enter an inventory id to select: ")
    duration = int(input("Enter recording duration in seconds: ") or 60)

    inventory = INVENTORY_MAP[int(inv_id)]
    primary = SERVER_MAP[inventory["location"]]
    primary_url = f'http://{primary["ip_address"]}:{primary["port"]}/inventory/{inv_id}'
    has_backup = True if (primary["partner_id"] is not None) else False    
    # Check if primary has backup
    if has_backup:
        backup = SERVER_MAP[primary["partner_id"]]
        backup_url = f'http://{backup["ip_address"]}:{backup["port"]}/inventory/{inv_id}'
    
    print("Starting experiment in 10 seconds...")
    start_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=10)
    stop_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)
    num_workers = mp.cpu_count()  

    for i in range(0, num_workers):
        process = Process(target=send_and_record, args=(f"primary_{stop_time}_worker_{i}.csv", primary_url, start_time, stop_time, "Primary",))
        process.start()
        if i == (num_workers - 1) :
            print("Running experiment...")
            process.join()
    
    # if has_backup:
    #     p2 = Process(target=send_and_record, args=(f"backup_{stop_time}.csv", backup_url, stop_time, "Backup",))
    #     p2.start()
    #     p2.join()
    # p1.join()
    print("Experiment completed!")
    
    # print(" -- Automated Request Frequency --")
    # print("1) Continuous (until stopped)")
    # print("2) Scheduled")
    # print("3) Fixed Number of Requests")
    # frequency = input("\nChoose a request frequency above: ")

    # print(" -- Inventory ID Scope --")
    # print("1) Single Inventory ID")
    # print("2) Random ID from Range")
    # scope = input("\nChoose a scope above: ")

    # match frequency:
    #         case "1":
    #             download_server_map()

    #         case "2":
    #             register_new_server()

    #         case "3":
    #             transfer_inventory()
            
    #         case _:
    #             print("Error: Selection did not match any options")

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
                sync_servers()

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
                send_requests()

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