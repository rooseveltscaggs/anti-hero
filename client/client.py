import requests

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

if __name__ == "__main__":
    make_request()
