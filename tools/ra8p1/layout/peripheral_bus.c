/* Independent RA8P1 HM R01UH1064EJ0130 Rev.1.30 anchors for bus interfaces. */
#include "peripheral_small.c"

/* HM41.2 pp.2461–2554: I3C scalar registers and sparse address-table banks. */
_Static_assert(sizeof(R_I3C0_Type) == 0x3E8, "I3C complete extent");
_Static_assert(R_I3C0_S_BASE == 0x4035F000, "I3C secure base");
_Static_assert(R_I3C0_NS_BASE == 0x5035F000, "I3C nonsecure base");
_Static_assert(offsetof(R_I3C0_Type, CECTL) == 0x10, "I3C clock enable");
_Static_assert(offsetof(R_I3C0_Type, NCMDQP) == 0x150, "I3C normal command queue");
_Static_assert(offsetof(R_I3C0_Type, NTDTBP0_BY) == 0x158, "I3C byte data view");
_Static_assert(sizeof(((R_I3C0_Type *) 0)->NTDTBP0_BY) == 1, "I3C byte port width");
_Static_assert(offsetof(R_I3C0_Type, DATBAS0) == 0x224, "I3C first device address");
_Static_assert(offsetof(R_I3C0_Type, DATBAS7) == 0x25C, "I3C final device address");
_Static_assert(offsetof(R_I3C0_Type, SDATBAS2) == 0x2B8, "I3C third slave address");
_Static_assert(offsetof(R_I3C0_Type, MSDCT7) == 0x2EC, "I3C final master characteristic");
_Static_assert(offsetof(R_I3C0_Type, SVDVAD2) == 0x338, "I3C third slave address");
_Static_assert(offsetof(R_I3C0_Type, SC2CPT) == 0x3E4, "I3C final capture register");
_Static_assert(R_I3C0_SVCTL_SVAEn_Msk == 0x70000, "I3C three slave-address enables");

/* HM37.2 pp.1977–2028: USBFS is a 16-bit FIFO interface. */
_Static_assert(sizeof(R_USB_FS0_Type) == 0x408, "USBFS extent includes standby registers");
_Static_assert(R_USB_FS0_S_BASE == 0x40250000, "USBFS secure base");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->CFIFO) == 2, "USBFS FIFO width");
/* HM37.2.4–5 Tables37.5–8: only the low byte is legal in 8-bit mode.
 * FSP5.9 calls the 16-bit view FIFOL and the low-byte view FIFOLL.
 */
_Static_assert(offsetof(R_USB_FS0_Type, CFIFOL) == 0x14, "USBFS halfword FIFO offset");
_Static_assert(offsetof(R_USB_FS0_Type, CFIFOLL) == 0x14, "USBFS byte FIFO offset");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->CFIFOL) == 2, "USBFS halfword FIFO view");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->CFIFOLL) == 1, "USBFS low-byte FIFO view");
_Static_assert(offsetof(R_USB_FS0_Type, D0FIFOL) == 0x18, "USBFS FIFO0 halfword offset");
_Static_assert(offsetof(R_USB_FS0_Type, D0FIFOLL) == 0x18, "USBFS FIFO0 byte offset");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->D0FIFOL) == 2, "USBFS FIFO0 halfword width");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->D0FIFOLL) == 1, "USBFS FIFO0 low-byte width");
_Static_assert(offsetof(R_USB_FS0_Type, D1FIFOL) == 0x1C, "USBFS FIFO1 halfword offset");
_Static_assert(offsetof(R_USB_FS0_Type, D1FIFOLL) == 0x1C, "USBFS FIFO1 byte offset");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->D1FIFOL) == 2, "USBFS FIFO1 halfword width");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->D1FIFOLL) == 1, "USBFS FIFO1 low-byte width");
_Static_assert(offsetof(R_USB_FS0_Type, D1FIFO) == 0x1C, "USBFS FIFO1 offset");
_Static_assert(offsetof(R_USB_FS0_Type, PIPE_CTR[8]) == 0x80, "USBFS ninth pipe");
_Static_assert(offsetof(R_USB_FS0_Type, PIPE6CTR) == 0x7A, "USBFS interrupt-pipe view");
_Static_assert(sizeof(R_USB_FS0_PIPE_TR_Type) == 4, "USBFS transaction pair stride");
_Static_assert(offsetof(R_USB_FS0_Type, PIPE_TR[4].E) == 0xA0, "USBFS final transaction enable");
_Static_assert(offsetof(R_USB_FS0_Type, PIPE_TR[4].N) == 0xA2, "USBFS final transaction counter");
_Static_assert(sizeof(((R_USB_FS0_Type *) 0)->DEVADD) == 12, "USBFS six device addresses only");
_Static_assert(offsetof(R_USB_FS0_Type, DEVADD[5]) == 0xDA, "USBFS final device address");
_Static_assert(offsetof(R_USB_FS0_Type, DPUSR0R_FS) == 0x400, "USBFS standby control");
_Static_assert(offsetof(R_USB_FS0_Type, DPUSR1R_FS) == 0x404, "USBFS standby interrupt");
_Static_assert(R_USB_FS0_SYSCFG_USBE_Msk == 1, "USBFS controller enable");

/* HM38.2 pp.2071–2129: USBHS supports all documented FIFO access widths. */
_Static_assert(sizeof(R_USB_HS0_Type) == 0x16C, "USBHS extent");
_Static_assert(R_USB_HS0_S_BASE == 0x40351000, "USBHS secure base");
_Static_assert(R_USB_HS0_NS_BASE == 0x50351000, "USBHS nonsecure base");
_Static_assert(sizeof(((R_USB_HS0_Type *) 0)->CFIFO) == 4, "USBHS word FIFO width");
_Static_assert(offsetof(R_USB_HS0_Type, CFIFOL) == 0x14, "USBHS low halfword");
_Static_assert(offsetof(R_USB_HS0_Type, CFIFOLL) == 0x14, "USBHS low byte");
_Static_assert(offsetof(R_USB_HS0_Type, CFIFOH) == 0x16, "USBHS high halfword");
_Static_assert(offsetof(R_USB_HS0_Type, CFIFOHH) == 0x17, "USBHS high byte");
_Static_assert(offsetof(R_USB_HS0_Type, D1FIFOHH) == 0x1F, "USBHS FIFO1 high byte");
_Static_assert(offsetof(R_USB_HS0_Type, DEVADD[9]) == 0xE2, "USBHS ninth device address");
_Static_assert(offsetof(R_USB_HS0_Type, DEVADDA) == 0xE4, "USBHS device A separate view");
_Static_assert(offsetof(R_USB_HS0_Type, DPUSR0R) == 0x160, "USBHS standby monitor");
_Static_assert(offsetof(R_USB_HS0_Type, DPUSRCR) == 0x16A, "USBHS standby command");
_Static_assert(R_USB_HS0_PHYSET_PLLRESET_Msk == 2, "USBHS PHY PLL reset, HM38.2.17 bit1");
