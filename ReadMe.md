# Building and Running

## Requirements
- Python 3.x
- PyQt5
- Linux environment for building and running the provided device simulator
  - for example: Ubuntu, WSL, or a Linux VM
- `make` and a C compiler such as `gcc`

## Setup
1. Open a terminal in the project root directory.
2. Install PyQt5:

   ```bash
   pip install PyQt5 or pip3 install PyQt5
   ```
3. run make in terminal 
1. Start one or more simulated devices using ./device with the required arguments.
2. In the project root directory, launch the GUI
3. create your devices by ./device ....
4. launch the GUI by doing 
```bash 
    python3 main.py
```
### Using the GUI

1. To discover a single device: enter the target IP address and port

2. click the discovery button

3. To discover multiple devices: use the multi-scan feature
4. only devices that are already running and reachable on the network will be found
5. Discovered devices will appear in the device list.
### To run a test:

1. tick the checkbox beside the device you want to test

2. enter the test duration

3. enter the response rate

4. click Start Test

5. To stop a running test, click Stop.

6. To open another device tab, click the Add Device Tab button at the top/right of the GUI.