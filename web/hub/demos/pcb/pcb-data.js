const BOARD_CORE = {
  name: "Laptop motherboard LM-9 reference design",
  outline: { width: 260, depth: 180, height: 1.6 },
  cell: 5,
  components: [
    {
      id: "cpu",
      name: "Main Processor",
      category: "processor",
      package: "BGA",
      position: { x: 0, y: 0, z: 0 },
      size: { w: 40, d: 40, h: 3 },
      color: "#1a1a1a",
      pins: 1200,
      description: "It executes all computation through multiple high-performance cores. It contains the integrated memory controller to directly interface with system RAM. It also includes integrated graphics for display output. Being soldered to the board is necessary because laptop form factors cannot accommodate a socket mechanism."
    },
    {
      id: "ram0",
      name: "Memory Slot 0",
      category: "memory",
      package: "SO-DIMM",
      position: { x: -60, y: 40, z: 0 },
      size: { w: 67, d: 30, h: 3 },
      color: "#000000",
      pins: 260,
      description: "They hold the system memory modules that provide volatile storage for running applications. They interface directly with the cpu memory controller over dedicated high-speed buses. They are latched connectors that physically secure the memory sticks while enabling electrical contact. This allows for user-upgradable memory in compatible laptop designs."
    },
    {
      id: "ram1",
      name: "Memory Slot 1",
      category: "memory",
      package: "SO-DIMM",
      position: { x: -60, y: -40, z: 0 },
      size: { w: 67, d: 30, h: 3 },
      color: "#000000",
      pins: 260,
      description: "They hold the system memory modules that provide volatile storage for running applications. They interface directly with the cpu memory controller over dedicated high-speed buses. They are latched connectors that physically secure the memory sticks while enabling electrical contact. This allows for user-upgradable memory in compatible laptop designs."
    },
    {
      id: "pch",
      name: "Platform Controller Hub",
      category: "chipset",
      package: "FCBGA",
      position: { x: 50, y: 0, z: 0 },
      size: { w: 35, d: 35, h: 2.5 },
      color: "#2a2a2a",
      pins: 1024,
      description: "It distributes the usb, pci express and sata lanes across the motherboard to various connectors and devices. It manages the boot process by coordinating with the bios to initialize hardware components. It acts as the central hub for chipset-level functionality. This enables communication between the processor and slower peripherals."
    },
    {
      id: "vrm1",
      name: "Voltage Regulator Module 1",
      category: "power",
      package: "Power Module",
      position: { x: 25, y: 20, z: 0 },
      size: { w: 15, d: 15, h: 2 },
      color: "#3a3a3a",
      pins: 50,
      description: "It switches the battery voltage down to the precise cpu core voltage required for operation. It stores energy temporarily in an inductor during the switching process. It filters the output with capacitors to smooth the voltage and reduce ripple. This provides stable, efficient power delivery to the processor."
    },
    {
      id: "vrm2",
      name: "Voltage Regulator Module 2",
      category: "power",
      package: "Power Module",
      position: { x: 25, y: -20, z: 0 },
      size: { w: 15, d: 15, h: 2 },
      color: "#3a3a3a",
      pins: 50,
      description: "It switches the battery voltage down to the precise cpu core voltage required for operation. It stores energy temporarily in an inductor during the switching process. It filters the output with capacitors to smooth the voltage and reduce ripple. This provides stable, efficient power delivery to the processor."
    },
    {
      id: "vrm3",
      name: "Voltage Regulator Module 3",
      category: "power",
      package: "Power Module",
      position: { x: -25, y: 0, z: 0 },
      size: { w: 15, d: 15, h: 2 },
      color: "#3a3a3a",
      pins: 50,
      description: "It switches the battery voltage down to the precise cpu core voltage required for operation. It stores energy temporarily in an inductor during the switching process. It filters the output with capacitors to smooth the voltage and reduce ripple. This provides stable, efficient power delivery to the processor."
    },
    {
      id: "bios",
      name: "Firmware Flash",
      category: "firmware",
      package: "SOP",
      position: { x: 70, y: 30, z: 0 },
      size: { w: 10, d: 8, h: 1 },
      color: "#000000",
      pins: 8,
      description: "It stores the UEFI firmware that contains the low-level code to start the machine. This firmware initializes hardware components before the operating system loads. It provides the interface between hardware and software during the boot sequence. The SPI bus allows for fast, reliable communication with the chipset."
    },
    {
      id: "ec",
      name: "Embedded Controller",
      category: "controller",
      package: "QFP",
      position: { x: 70, y: -30, z: 0 },
      size: { w: 12, d: 12, h: 1.5 },
      color: "#000000",
      pins: 100,
      description: "It runs the keyboard matrix scanning and input processing independently of the main cpu. It manages battery charging algorithms to protect the battery and optimize lifespan. It controls fan speeds based on temperature readings from various sensors. This ensures these critical functions remain available even when the main system is powered off."
    },
    {
      id: "wifi",
      name: "Wireless Module Slot",
      category: "wireless",
      package: "M.2",
      position: { x: 60, y: 60, z: 0 },
      size: { w: 22, d: 30, h: 2 },
      color: "#000000",
      pins: 75,
      description: "It carries the Wi-Fi and Bluetooth module that provides wireless connectivity to the system. It uses pci express for high-speed data transfer to support modern wireless standards. It also uses usb for additional connectivity and power delivery to the module. This enables seamless wireless communication for the laptop."
    }
  ]
};
