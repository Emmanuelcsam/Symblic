const BOARD_PARTS = {
  components: [
    // Capacitors (14 total): MLCC packages, passive category
    {
      id: "cap1",
      name: "cap1",
      category: "passive",
      package: "0603",
      position: { x: 10.0, y: 15.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.5 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor absorbs high-frequency noise on the CPU core power rail. Ceramic dielectric provides low ESR and excellent high-frequency response. Positioned adjacent to the CPU voltage regulator, it stabilizes the supply under transient loads."
    },
    {
      id: "cap2",
      name: "cap2",
      category: "passive",
      package: "0402",
      position: { x: 12.0, y: 17.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.3 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor filters noise on the PCH power rail. The ceramic dielectric material offers high capacitance density and temperature stability. It is placed close to the PCH to minimize power distribution impedance."
    },
    {
      id: "cap3",
      name: "cap3",
      category: "passive",
      package: "0805",
      position: { x: 14.0, y: 19.0, z: 0.0 },
      size: { w: 2.0, d: 1.2, h: 0.6 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor decouples the 1.8V regulator output rail. Ceramic dielectrics such as X7R provide stable capacitance across voltage and temperature ranges. It prevents voltage droop during CPU load transitions."
    },
    {
      id: "cap4",
      name: "cap4",
      category: "passive",
      package: "0603",
      position: { x: 16.0, y: 21.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.5 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor serves the CPU VCCIO rail. The ceramic dielectric construction enables low-inductance response to rapid current demands. It is part of the distributed decoupling network across the motherboard."
    },
    {
      id: "cap5",
      name: "cap5",
      category: "passive",
      package: "0402",
      position: { x: 18.0, y: 23.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.3 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor decouples the 3.3V auxiliary power rail. Ceramic capacitors are ideal for high-frequency noise filtering due to their parasitic characteristics. It prevents noise coupling into sensitive analog circuits."
    },
    {
      id: "cap6",
      name: "cap6",
      category: "passive",
      package: "0805",
      position: { x: 20.0, y: 25.0, z: 0.0 },
      size: { w: 2.0, d: 1.2, h: 0.6 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor stabilizes the PCH analog power domain. The ceramic dielectric provides consistent performance across operating temperatures. It is placed near the PCH to suppress switching noise."
    },
    {
      id: "cap7",
      name: "cap7",
      category: "passive",
      package: "0603",
      position: { x: 22.0, y: 27.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.5 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor filters the 5V standby power rail. Ceramic dielectric materials like X5R offer excellent volumetric efficiency for bulk decoupling. It ensures clean power delivery during sleep states."
    },
    {
      id: "cap8",
      name: "cap8",
      category: "passive",
      package: "0402",
      position: { x: 24.0, y: 29.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.3 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor supports the CPU VCCSA rail. The ceramic dielectric provides low-loss high-frequency noise absorption. It is part of the multi-stage filtering network."
    },
    {
      id: "cap9",
      name: "cap9",
      category: "passive",
      package: "0805",
      position: { x: 26.0, y: 31.0, z: 0.0 },
      size: { w: 2.0, d: 1.2, h: 0.6 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor decouples the memory power rail. Ceramic dielectrics enable compact high-capacitance values with excellent frequency response. It prevents voltage sag during memory burst operations."
    },
    {
      id: "cap10",
      name: "cap10",
      category: "passive",
      package: "0603",
      position: { x: 28.0, y: 33.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.5 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor is placed near the voltage regulator module input. The ceramic dielectric construction provides stable capacitance over time and temperature. It filters noise from the battery input before regulation."
    },
    {
      id: "cap11",
      name: "cap11",
      category: "passive",
      package: "0402",
      position: { x: 30.0, y: 35.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.3 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor provides decoupling for the PCH PCIe power domain. Ceramic dielectric offers low equivalent series resistance for effective high-frequency filtering. It maintains stable voltage during high-speed data transfers."
    },
    {
      id: "cap12",
      name: "cap12",
      category: "passive",
      package: "0805",
      position: { x: 32.0, y: 37.0, z: 0.0 },
      size: { w: 2.0, d: 1.2, h: 0.6 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor serves the CPU graphics power rail. The ceramic dielectric provides the necessary high-frequency response for GPU operations. It is positioned adjacent to the CPU package for optimal performance."
    },
    {
      id: "cap13",
      name: "cap13",
      category: "passive",
      package: "0603",
      position: { x: 34.0, y: 39.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.5 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC capacitor decouples the system agent power rail. Ceramic dielectric materials are chosen for their reliability and stability in motherboard applications. It prevents noise from affecting CPU-to-PCH communication."
    },
    {
      id: "cap14",
      name: "cap14",
      category: "passive",
      package: "0402",
      position: { x: 36.0, y: 41.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.3 },
      color: "#FFA500",
      pins: 2,
      description: "This MLCC decoupling capacitor is placed near the PCH south bridge section. The ceramic dielectric provides low-inductance paths for high-frequency currents. It helps maintain clean power delivery across the entire board."
    },

    // Resistors (8 total): passive category
    {
      id: "res1",
      name: "res1",
      category: "passive",
      package: "0402",
      position: { x: 50.0, y: 10.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.2 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor provides a pull-up on the shared I2C bus SDA line. Pull-up resistors are essential for I2C communication to ensure the bus floats high when no device is driving it. The value is chosen to meet rise time requirements without excessive current draw."
    },
    {
      id: "res2",
      name: "res2",
      category: "passive",
      package: "0402",
      position: { x: 52.0, y: 12.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.2 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor provides a pull-up on the shared I2C bus SCL line. Together with the SDA pull-up, it ensures proper bus operation across all connected devices. I2C is an open-drain bus requiring external pull-ups for correct logic levels."
    },
    {
      id: "res3",
      name: "res3",
      category: "passive",
      package: "0603",
      position: { x: 54.0, y: 14.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.3 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor provides termination for the DDR4 memory data line DQ0. Memory termination resistors match the transmission line impedance to prevent signal reflections. They are critical for maintaining signal integrity at high data rates."
    },
    {
      id: "res4",
      name: "res4",
      category: "passive",
      package: "0603",
      position: { x: 56.0, y: 16.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.3 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor provides termination for the DDR4 memory data line DQ7. Each data line requires proper termination to ensure reliable operation at the JEDEC-defined speeds. The resistor value is calculated based on the PCB trace characteristics."
    },
    {
      id: "res5",
      name: "res5",
      category: "passive",
      package: "0402",
      position: { x: 58.0, y: 18.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.2 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor is part of the voltage divider network for analog sensing. Voltage dividers scale voltages to levels compatible with ADC inputs. It ensures accurate measurement of battery voltage for power management."
    },
    {
      id: "res6",
      name: "res6",
      category: "passive",
      package: "0402",
      position: { x: 60.0, y: 20.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.2 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor limits current through an LED indicator on the board. Current-limiting resistors protect LEDs from excessive current that would damage them. The value is calculated based on the LED forward voltage and desired brightness."
    },
    {
      id: "res7",
      name: "res7",
      category: "passive",
      package: "0603",
      position: { x: 62.0, y: 22.0, z: 0.0 },
      size: { w: 1.6, d: 0.8, h: 0.3 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor provides a weak pull-down for an unused GPIO pin. Unused pins should be tied to a defined logic level to prevent floating inputs. A pull-down ensures the pin reads as logic low when not actively driven."
    },
    {
      id: "res8",
      name: "res8",
      category: "passive",
      package: "0402",
      position: { x: 64.0, y: 24.0, z: 0.0 },
      size: { w: 1.0, d: 0.5, h: 0.2 },
      color: "#8B4513",
      pins: 2,
      description: "This resistor forms part of the bias network for the audio codec reference voltage. Audio circuits require stable reference voltages for proper analog operation. The resistor network divides the supply to create the midpoint bias."
    },

    // Inductors (4 total): passive category
    {
      id: "ind1",
      name: "ind1",
      category: "passive",
      package: "4.5x4.5mm",
      position: { x: 80.0, y: 10.0, z: 0.0 },
      size: { w: 4.5, d: 4.5, h: 2.0 },
      color: "#808080",
      pins: 2,
      description: "This power inductor stores energy in a magnetic field when current flows through it. It smooths the switched regulator output by resisting changes in current. The ferrite core material provides high inductance with low DC resistance."
    },
    {
      id: "ind2",
      name: "ind2",
      category: "passive",
      package: "4.5x4.5mm",
      position: { x: 85.0, y: 15.0, z: 0.0 },
      size: { w: 4.5, d: 4.5, h: 2.0 },
      color: "#808080",
      pins: 2,
      description: "This inductor is part of the CPU core voltage regulator module output filter. It stores energy in a magnetic field during the switch on-phase and releases it during the off-phase. This smoothing action reduces voltage ripple at the CPU power input."
    },
    {
      id: "ind3",
      name: "ind3",
      category: "passive",
      package: "3.0x3.0mm",
      position: { x: 90.0, y: 20.0, z: 0.0 },
      size: { w: 3.0, d: 3.0, h: 1.5 },
      color: "#808080",
      pins: 2,
      description: "This inductor smooths the switched regulator output for the GPU power rail. By storing energy in a magnetic field, it reduces high-frequency switching noise. The shielding on the component prevents magnetic interference with nearby circuits."
    },
    {
      id: "ind4",
      name: "ind4",
      category: "passive",
      package: "3.0x3.0mm",
      position: { x: 95.0, y: 25.0, z: 0.0 },
      size: { w: 3.0, d: 3.0, h: 1.5 },
      color: "#808080",
      pins: 2,
      description: "This inductor filters the PCH power supply from the regulator. It stores energy in a magnetic field and smooths the output current. The laminated core structure minimizes eddy current losses at high switching frequencies."
    },

    // Crystals (2 total): clock category
    {
      id: "xtal1",
      name: "xtal1",
      category: "clock",
      package: "3225",
      position: { x: 110.0, y: 10.0, z: 0.0 },
      size: { w: 3.2, d: 2.5, h: 0.8 },
      color: "#C0C0C0",
      pins: 2,
      description: "This is a 32.768 kHz crystal resonator for the real-time clock circuit. It provides the precise timekeeping reference needed to maintain accurate date and time when the system is powered off. Boards need a low-frequency RTC crystal for timekeeping and a high-frequency system clock for CPU operation."
    },
    {
      id: "xtal2",
      name: "xtal2",
      category: "clock",
      package: "7050",
      position: { x: 115.0, y: 15.0, z: 0.0 },
      size: { w: 7.0, d: 5.0, h: 1.2 },
      color: "#C0C0C0",
      pins: 2,
      description: "This is a 24 MHz crystal oscillator serving as the chipset clock source. It provides the primary timing reference for the CPU, PCH, and most high-speed peripherals. Boards need both a high-frequency system clock for processing and a low-frequency RTC clock for timekeeping to cover all timing requirements."
    },

    // Audio components (2 total): audio category
    {
      id: "codec1",
      name: "audio_codec",
      category: "audio",
      package: "QFN-48",
      position: { x: 130.0, y: 10.0, z: 0.0 },
      size: { w: 7.0, d: 7.0, h: 0.9 },
      color: "#4169E1",
      pins: 48,
      description: "This audio codec chip handles analog-to-digital and digital-to-analog conversion for the system. It supports multiple input and output channels with configurable sample rates and bit depths. The integrated headphone amplifier drives the audio jack directly."
    },
    {
      id: "jack1",
      name: "audio_jack",
      category: "audio",
      package: "3.5mm",
      position: { x: 135.0, y: 15.0, z: 0.0 },
      size: { w: 15.0, d: 8.0, h: 6.0 },
      color: "#228B22",
      pins: 4,
      description: "This 3.5mm audio jack connector provides analog audio output for headphones and line-out. It supports TRRS configuration for headsets with microphone input. The shielded housing prevents electromagnetic interference from affecting audio quality."
    },

    // IO connectors (4 total): io category
    {
      id: "usbc1",
      name: "usbc1",
      category: "io",
      package: "USB-C",
      position: { x: 150.0, y: 10.0, z: 0.0 },
      size: { w: 8.4, d: 3.0, h: 4.0 },
      color: "#000000",
      pins: 24,
      description: "This USB-C port supports data transfer, power delivery, and display output. The configuration channel pins allow the port to negotiate power delivery contracts with connected devices. USB Power Delivery negotiation determines power direction and voltage levels dynamically."
    },
    {
      id: "usbc2",
      name: "usbc2",
      category: "io",
      package: "USB-C",
      position: { x: 155.0, y: 15.0, z: 0.0 },
      size: { w: 8.4, d: 3.0, h: 4.0 },
      color: "#000000",
      pins: 24,
      description: "This USB-C port provides full-featured connectivity including SuperSpeed data and power delivery. The configuration channel pins enable detection of cable orientation and connection type. USB Power Delivery negotiation allows the system to source or sink power at various voltage levels."
    },
    {
      id: "hdmi1",
      name: "hdmi",
      category: "io",
      package: "HDMI-Type-A",
      position: { x: 160.0, y: 10.0, z: 0.0 },
      size: { w: 14.0, d: 5.0, h: 4.5 },
      color: "#000000",
      pins: 19,
      description: "This HDMI port provides high-definition video and audio output to external displays. It supports multiple video resolutions and refresh rates. The connector includes TMDS data channels, clock channel, and DDC for EDID communication."
    },
    {
      id: "edp1",
      name: "edp",
      category: "io",
      package: "eDP",
      position: { x: 165.0, y: 15.0, z: 0.0 },
      size: { w: 20.0, d: 5.0, h: 3.0 },
      color: "#000000",
      pins: 40,
      description: "This eDP display connector carries video and control signals to the internal panel. It supports high-resolution displays with embedded clock and data channels. The connector includes power lines for the panel backlight and control signals."
    },

    // Connectors (4 total): connector category
    {
      id: "batt1",
      name: "battery",
      category: "connector",
      package: "custom",
      position: { x: 180.0, y: 10.0, z: 0.0 },
      size: { w: 25.0, d: 12.0, h: 5.0 },
      color: "#FFD700",
      pins: 8,
      description: "This battery connector provides the main power input to the system from the battery pack. It carries the main power rails and battery management system signals. The connector includes temperature sensing and authentication lines for battery safety."
    },
    {
      id: "fan1",
      name: "fan",
      category: "connector",
      package: "3-pin",
      position: { x: 185.0, y: 15.0, z: 0.0 },
      size: { w: 8.0, d: 5.0, h: 3.0 },
      color: "#000000",
      pins: 3,
      description: "This fan connector supplies power and PWM control signals to the system cooling fan. It provides ground, 12V power, and a tachometer signal for speed monitoring. The PWM signal allows variable speed control based on system temperature."
    },
    {
      id: "kbd1",
      name: "keyboard",
      category: "connector",
      package: "FPC",
      position: { x: 190.0, y: 20.0, z: 0.0 },
      size: { w: 30.0, d: 2.0, h: 1.0 },
      color: "#000000",
      pins: 20,
      description: "This keyboard connector interfaces with the built-in keyboard matrix and backlight control. It carries scan lines, data lines, and power for the keyboard LEDs. The flexible flat cable design allows for reliable connection in the laptop assembly."
    },
    {
      id: "touch1",
      name: "touchpad",
      category: "connector",
      package: "FPC",
      position: { x: 195.0, y: 25.0, z: 0.0 },
      size: { w: 25.0, d: 2.0, h: 1.0 },
      color: "#000000",
      pins: 12,
      description: "This touchpad connector carries I2C or PS/2 signals from the touchpad sensor to the embedded controller. It provides power and data connections for the touchpad interface. The fine-pitch connector ensures reliable signal integrity for precise cursor control."
    },

    // Mechanical (6 total): mechanical category
    {
      id: "tp1",
      name: "tp1",
      category: "mechanical",
      package: "test_point",
      position: { x: 210.0, y: 10.0, z: 0.0 },
      size: { w: 1.5, d: 1.5, h: 0.5 },
      color: "#FF0000",
      pins: 1,
      description: "This test point provides a convenient probe location for debugging and verification. It allows engineers to measure signal voltages and verify circuit operation during development. The exposed metal surface enables easy contact with test probes and oscilloscope leads."
    },
    {
      id: "tp2",
      name: "tp2",
      category: "mechanical",
      package: "test_point",
      position: { x: 212.0, y: 12.0, z: 0.0 },
      size: { w: 1.5, d: 1.5, h: 0.5 },
      color: "#FF0000",
      pins: 1,
      description: "This test point serves as a ground reference for measurement purposes. It provides a common return path for differential voltage measurements across the board. The plated surface ensures good electrical contact and prevents oxidation over time."
    },
    {
      id: "hole1",
      name: "hole1",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 0.0, y: 0.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the top-left corner of the board. It provides a mechanical mounting point for securing the PCB to the chassis. The plating ensures electrical connectivity to ground for EMI shielding and safety."
    },
    {
      id: "hole2",
      name: "hole2",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 240.0, y: 0.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the top-right corner of the board. It provides structural support and mechanical attachment to the laptop frame. The through-plating connects to the internal ground plane for improved shielding."
    },
    {
      id: "hole3",
      name: "hole3",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 0.0, y: 160.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the bottom-left corner of the board. It secures the PCB to the chassis and provides an electrical ground connection. The hole is placed to distribute mechanical stress evenly across the board."
    },
    {
      id: "hole4",
      name: "hole4",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 240.0, y: 160.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the bottom-right corner of the board. It provides a secure mounting point and ground connection for the PCB assembly. The plating thickness is sufficient to carry fault currents safely to chassis ground."
    },
    {
      id: "hole5",
      name: "hole5",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 120.0, y: 0.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the mid-point of the top edge. It provides additional mechanical support for the PCB in the center region. The hole is connected to the ground plane to minimize flex and improve thermal dissipation."
    },
    {
      id: "hole6",
      name: "hole6",
      category: "mechanical",
      package: "mounting_hole",
      position: { x: 120.0, y: 160.0, z: 0.0 },
      size: { w: 3.5, d: 3.5, h: 1.6 },
      color: "#A9A9A9",
      pins: 0,
      description: "This plated mounting hole is positioned near the mid-point of the bottom edge. It provides central mechanical support for the PCB assembly. The connection to ground helps with electromagnetic interference shielding and mechanical stability."
    }
  ],

  nets: [
    {
      id: "net1",
      from: "cpu",
      to: "ram0",
      width: 4,
      label: "cpu_to_ram0_memory_bus",
      kind: "data"
    },
    {
      id: "net2",
      from: "cpu",
      to: "ram1",
      width: 4,
      label: "cpu_to_ram1_memory_bus",
      kind: "data"
    },
    {
      id: "net3",
      from: "vrm1",
      to: "cpu",
      width: 8,
      label: "vrm1_to_cpu_core_power",
      kind: "power"
    },
    {
      id: "net4",
      from: "batt1",
      to: "vrm1",
      width: 6,
      label: "battery_to_vrm1_input_power",
      kind: "power"
    },
    {
      id: "net5",
      from: "cpu",
      to: "pch",
      width: 5,
      label: "cpu_to_pch_dmi_link",
      kind: "data"
    },
    {
      id: "net6",
      from: "pch",
      to: "bios",
      width: 2,
      label: "pch_to_bios_spi_bus",
      kind: "control"
    },
    {
      id: "net7",
      from: "pch",
      to: "wifi",
      width: 3,
      label: "pch_to_wifi_pci_express",
      kind: "data"
    },
    {
      id: "net8",
      from: "xtal1",
      to: "ec",
      width: 1,
      label: "xtal1_to_ec_clock",
      kind: "control"
    },
    {
      id: "net9",
      from: "xtal2",
      to: "pch",
      width: 1,
      label: "xtal2_to_pch_clock",
      kind: "control"
    },
    {
      id: "net10",
      from: "ec",
      to: "fan1",
      width: 2,
      label: "ec_to_fan_control",
      kind: "control"
    },
    {
      id: "net11",
      from: "codec1",
      to: "jack1",
      width: 2,
      label: "codec_to_audio_jack",
      kind: "data"
    },
    {
      id: "net12",
      from: "usbc1",
      to: "pch",
      width: 3,
      label: "usbc1_to_pch",
      kind: "data"
    },
    {
      id: "net13",
      from: "pch",
      to: "edp1",
      width: 4,
      label: "pch_to_display_connector",
      kind: "data"
    }
  ]
};
