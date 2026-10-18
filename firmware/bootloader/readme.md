# HD Blind second-stage bootloader

BGM13P22F512GA, Gecko SDK 4.4.6. Secure-boot enforcement disabled for development.
Preserve the factory first-stage page. Slot 0 is 0x40000–0x77000; NVM3 starts at 0x77000.

The installer preserves the existing first-stage page at 0x0FE10000. Only the
seven second-stage pages at 0x0FE10800–0x0FE14000 are replaced. The SDK SLC
project is generated for BGM13P22F512GA. Build its ELF target, then use
Simplicity Commander convert --crc to produce the second-stage image. The
SDK's combined-first-stage post-build target is intentionally not installed.

The RAM writer links Silicon Labs emlib `em_msc.c` from the pinned SDK. Compile
for Cortex-M4/Thumb, EFR32BG13P632F512GM48, using `ram_writer.ld`; include the
SDK device, CMSIS/Core, emlib and platform/common include directories. Use
-Os -ffreestanding -ffunction-sections -fdata-sections -nostdlib and
-Wl,--gc-sections. Entry is 0x20008000; image source is 0x20000000;
result is 0x20007000. 0x4844424c means all seven pages were verified.

Application enrollment keys live in main-flash NVM3 and are preserved by this
update. The existing HA entry can reconnect; new enrollments use the MAC-based
default device name. Bootloader and application OTA remain separate work.
