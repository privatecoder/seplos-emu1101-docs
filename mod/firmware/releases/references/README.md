# EMU1101-EXT reference metadata

> **Port notation:** **UART0 = RS485-1/RS485-2 (shared pack bus)**; **UART1 = RS485 pair in the CAN socket**; **UART2 = local display/Bluetooth port**. UART1 carries RS485 traffic; the actual CAN interface uses separate pins in the same socket.

These manifests bind the byte-identical EXT05 Light 1.5.4/1.5.5 and Full 1.6.4/1.6.5/1.6.6 reference builds. All five builders remain supported for reproduction.

Light 1.5.4 / Full 1.6.4 retain the controlled OEM scheduler flag-loss behavior. Light 1.5.5 / Full 1.6.5 include atomic scheduler cleanup. The four .4/.5 images retain the OEM fixed UART0 polling dwell; early valid-response completion starts with Light 1.5.6 / Full 1.6.6.

[Current release identities](../README.md)

Full 1.6.6 includes early polling and the fixed 1 A ordinary CCL ramp; Full 1.6.7 adds the separate configurable downward step.
