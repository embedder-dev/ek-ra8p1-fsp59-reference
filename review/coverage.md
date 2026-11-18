# Independent primary-source review coverage

## Frozen inputs

- Snapshot: [`evidence/initial-snapshot.json`](evidence/initial-snapshot.json), SHA-256 `c9ebdeb6abb22eff539188cffd8e234103a485ec3b360bd4209ea94177b23094`; 4,473 hashed files. Tracks outer and nested Git HEAD, tracked changes and untracked paths. Nested original FSP 5.9 HEAD: `5e8fbb10c752e16272790bd3a2587485d0377835`.
- All snapshot input hashes were checked again after reference acquisition: zero changed inputs. Production, metadata, generators and tests remain frozen until all initial reviews are recorded.
- References: [`evidence/primary-references.json`](evidence/primary-references.json): 2,130 HM Markdown files (R01UH1064EJ0130 Rev.1.30), 75 datasheet Markdown files, all13 supplied technical-update trees, EK-RA8P1 user manual R20UT5309EG0104 and errata R20ZZ0244EG0200 PDFs, Arm CM85 TRM `101924_0101_07_en` and CM33 TRM `100230_0100_08_en` PDFs with source URLs and hashes.
- SVD: [`evidence/svd-primary-inventory.json`](evidence/svd-primary-inventory.json): supplied parsed `.embedder/svd-cache/R7KA8P1AD.json`, version 1.10.02; SHA-256 `e72e5b85682d5bb01b669187d47173211e794bf25d882b432dbb8a4f3a4ccf65`; 257 peripheral records, 7,920 register records, 43,053 field records (includes aliases). No source XML located in the project. AD applicability to fitted KF is not assumed; reviewers must reconcile against datasheet Table 1.15 and HM.
- Supplied pin-model filenames and bytes, candidate packs and authoring inputs are included in the snapshot. No pin-model edit is permitted.
- No hardware access, tests, builds, generation or IDE operation has occurred during initial review.

## Independence and review barrier

Every reviewer below is a newly launched session, not a resumed implementation author. Reviewers may only read primary sources, candidate code as the subject, and original FSP 5.9 code for conventions. They must not read prior agent reports, migration notes or test results. No reviewer may edit, run tests/builds, generate files, use the IDE or access hardware. The parent alone records reports. Initial findings must all be recorded before any fix or mutation test.

The server permits ten active agents. Remaining assignments are queued here, not represented as running. Each changed driver/port receives its own fresh reviewer.

| Area / disjoint scope | Fresh task ID | State | Checked scope / findings |
|---|---|---|---|
| Driver: DAC_B | task_mwkd69bs_3ca809 | Initial review returned | Five entrypoints, four helpers, full header/MDF; DAC-001; runtime/measurement and pair ownership unverified |
| Driver: PDM | task_mwkd69bu_b5a39b | Initial review returned | Six APIs, six helpers, both ISRs, full API/instance/MDF; PDM-001–004; actual FIFO/IRQ/timing unverified |
| Driver: MRAM | task_mwkd69bv_d3057e | Initial review returned | 19 public APIs, six helpers, full header/MDF incl guards; MRAM-001–007; binary callgraph/runtime not reviewed |
| Driver: CGC | task_mwkd69bw_fb8386 | Initial review returned | 12 API entries/all helpers, PLL P/Q/R math, overrides/MDF/callback/checking branches; CGC-001–010; BSP wait-state/voltage review separate |
| Driver: ADC_B | task_mwkd69bx_33bedb | Initial review and bounded continuation returned | 14 APIs/28 ISRs/full headers/MDF; ADC-001–018; S&H ordering/occupancy/mode, differential/source exclusion and FIFO MMIO reviewed |
| Driver: WDT | task_mwkd69by_72cdaf | Initial review returned | All 11 functions, full headers/MDF; WDT-001–003; runtime/compiler not exercised; AD SVD binary-enumeration discrepancy noted |
| Header: system/core/security/bus/DMA/ICU | task_mwkd86pr_ad7c28 | Initial review returned | 52 peripheral aliases/1196 register records/4271 fields; HDR-C01–09 and HDR-A02; expanded dimensions/reset-mask source limitations |
| Header: timers/serial/storage | task_mwkd86pu_0d2534 | Initial review returned | 94 SVD peripheral entries,2905 register records,20812 fields incl aliases;2823 register records matched;GPTP82 records omitted;HDR-T01–06 |
| Header: analog/audio/MRAM/CRC/CAC/DOC | task_mwkd86pt_e1452a | Initial review returned | 32 SVD objects/593 register records/2100 fields plus MWMCR; 100 type padding spans/125 instance spans; HDR-A01–03; comparator superset restrictions retained |
| Header: graphics/connectivity/ports/remaining primary blocks | task_mwkd86pu_7e5992 | Initial review returned | 72 peripherals/3268 register records/15796 fields;24 missing peripheral aliases; HDR-G01–16 and deduplicated GPTP HDR-T01; resets/NPU details remain source gaps |
| Interrupt/event table and routing | task_mwkdbd0p_0b7655 | Initial review returned | 493 enums/268 aliases,490 ICU+320 ELC rows,492 MDF entries/3444 scope checks,26 links,15 NMI bits; EVT-001–003 |
| BSP clocks/limits/transitions | task_mwkdbd0r_25ccb4 | Initial review returned; numerical continuation pending | CLK-001–013 and BSP-005 duplicate;98 nodes/29 constraints/2567 options inventoried; exhaustive numeric/product/voltage matrix not yet established |
| BSP startup/memory/security/protection | task_mwkdbklx_d41d45 | Initial review returned; source clarification recorded | 24 subject files plus14 staged counterpart comparisons; BSP-001–006; stack-seal and boot-FSBL policy unresolved |
| Dual-core and CPU1 project | task_mwkdd3rt_a95b51 | Initial review returned | Flat pair source/compiler/debug/linker/dependency/allocations; DUAL-001–003; no peripheral IRQs, nondefault security/IPC/runtime remain gaps |
| Driver: AGT | task_mwkdghnx_1d4cc1 | Initial review returned | 19 C definitions/13 public APIs/5 helpers/ISR; full instance/API/MDF; allegations split AGT-001–022 |
| Driver: ICU | task_mwkdnp34_76dbb9 | Initial review returned | All five APIs/ISR/full headers/MDF; ICU-001–005; inherited issues, ownership/runtime not verified |
| Driver: I3C | task_mwkdi4rn_009a06 | Initial review returned | Full C/API/instance/MDF; I3C-001–009 |
| Driver: LPM | task_mwkdpnk4_3784ed | Initial review returned | 5 APIs/6 helpers/full headers/MDF; LPM-001–010 |
| Driver: SCI_B SPI | task_mwkdqz2b_40b1ad | Initial review returned | 17 functions/27 register sites/full headers/MDF; SCISPI-001–004 |
| Driver: GLCDC | task_mwkdqz2t_12815e | Initial review returned | 11 APIs/28 helpers/3 ISRs/173 MDF properties/140 constraints; GLCDC-001–014 split by repair owner |
| Driver: MIPI DSI | task_mwkdrquw_c4ca1f | Initial review returned | 28 functions, both headers, full MDF; DSI-001–011; runtime/optional generation unverified |
| Port: FreeRTOS | task_mwkdstci_919d2a | Initial review returned | Entire port/portmacro/bothMDFs; FREERTOS-001–008; BASEPRI/context/concurrency qualifications open |
| Port: ThreadX | task_mwkdtuip_cfabce | Initial review returned | All19non-IARfiles/kernel/CMSIS/MDF contracts; THREADX-001–004; IAR/runtime not qualified |
| Board/configurator/packs | task_mwkdl3g9_01f369 | Initial and bounded continuation returned | CFG-001–006; board/model/pack tooling checked; remaining security and ADC semantic review assigned fresh specialists |
| Older devices | task_mwkdljbt_7af8c6 | Initial review returned | All96 changed tracked owners and relevant untracked production/pack inputs; OLD-001; static preservation only |
| Tests: initial selection | task_mwkdlzvo_d10a2b | Partial initial review returned | TEST-001–004; exact unreviewed remainder assigned fresh continuations; not exhaustive |

## Coverage accounting

Whole-system review coverage is not complete. Returned driver reviews are initial static reviews, not software or hardware qualification. Findings counts, reviewed register/event/file lists and explicit uncovered scope will be recorded from each returned report. A partial or timed-out review triggers a bounded fresh continuation; it is never an exhaustive pass. SVD/manual disagreements and source availability gaps remain distinct from confirmed production defects.

### Header timer/serial/storage exact initial scope

GPT320–GPT3213 (28/1540/14476 peripheral/register/field records), GPT_OPS(2/2/34), GPT_GTCLK(2/2/2), GPTP(2/82/102), POEG(2/8/120), AGT0–1(4/40/96), ULPT0–1(4/40/116), WDT0–1(4/20/36), IWDT(2/10/20), SCI0_B–SCI9_B(20/540/3600), SPI0_B–SPI1_B(4/56/300), IIC0–2(6/51/240), IIC0WU(2/4/16), I3C(2/186/570), RTC(2/72/168), OSPI0_B–1_B(4/132/552), SDHI0–1(4/120/364). Counts include secure/nonsecure aliases and unexpanded range records. Reviewer reports all2823 emitted-correspondence records match addresses/width/access/field coverage;GPTP remains omitted. Reset constants are not emitted, and underlying321 manual sections were compared without inventing zeros for RTC unknown/SDHI pin-dependent resets. Incomplete secure IIC SVD descriptions were reconciled from HM40.2. No runtime result implied.

### Analog/audio/MRAM header coverage and reconciliations

Reviewer task_mwkd86pt_e1452a checked TSD(0/1), MRAM(20/92), CAC(24/96), DAC0_B/DAC1_B(31,158/103,212), TSN(32/104), ACMPHS0–3(33,159–161/105,213–215), PDMIF(36/108), SSIE0–1(37,163/109,217), CRC(42/114), DOC_B(43/115), ADC_B(48/120), plus both SYSC.MWMCR records. Indexes refer to primary SVD peripheral array; every contained register/field was included. Expanded represented header views:649 registers/access views and2291 fields across physical instances;100 type-level padding spans/125 expanded instance spans. AD is single-core/512KB versus fitted KF dual-core/1MB, so shared peripheral facts were reconciled via HM1.3/1.4 and datasheet1.15. HM supplements SVD omissions in ADC ADEXDR/NS ADFIFOCR and identification; PDM coefficient n=0..2 derived from HM50.2.31. Comparator CSTEN/VREFEN superset must not imply availability on instances1–3. Header emits no reset constants:293 fixed SVD-reset records were compared; TSD/identity and state/configuration-dependent resets are not asserted zero.

### Initial event and dual-core coverage gaps

Event review: all490 ICU and320 ELC rows,493 enums including NONE,268 aliases,492 MDF entries/490 unique events/3444 memberships,26 link targets,15 NMI enum bits;139 stock driver MDF event/template comparisons and two new PDM interrupts. No target event/link/scope entry left unreviewed per reviewer; runtime/security routing still unverified. Dual-core review inspected the existing flat pair only: both have zero peripheral IRQs. Cache-coherent IPC, peripheral contention, nondefault security, reset/restart and emitted null-address scrub instructions are not cleared by that static pair review.

### I3C initial review returned

Fresh reviewer task_mwkdi4rn_009a06 inspected the entire driver, instance/API headers and MDF. Nine allegations I3C-001–009 (1 High,7 Medium,1 Low) recorded; C issues reported inherited from original5.9. Headers compared with original HEAD; original MDF byte comparison unavailable to reviewer. No qualification implied. HM41 and applicable TU used; KF-specific pin validation remains outside this driver review.

### BSP startup review source clarification

Task_mwkdbklx_d41d45 confirms inspected header was R7KA8P1KF.h; AD.h was a reporting typo. Its24 logical subjects exclude staged duplicates. MPU evidence is original release archive `reference/vendor/FSP_Packs_v5.9.0.zip`, nested `Arm.CMSIS6.6.1.0+fsp.5.9.0.pack`, entry `ra/arm/CMSIS_6/CMSIS/Core/Include/m-profile/armv8m_mpu.h:149–162`, SHA256 `287fcabda261890f568009423ab2beb163bdcc9af591b4ce9e28f4e465f4e202`. Fifth RBAR argument is XN; RLAR limit is one-extended. No moving upstream URL is needed. Capability/header-generation/pack owners and supporting BSP security/protection/compiler headers were not exhaustively reviewed by this specialist and must be covered separately.

### Core/system primary-header review returned

Task_mwkd86pr_ad7c28 inspected52 SVD peripheral aliases: RMPU,SRAM,BUS,ICU_COMMON,CPSCU,DMAC00–07,DMA0,DTC0,ICU,CPU_CTRL,CPU_OCD,CPU_DBG,CACHE,FCACHE,TCM,SYSC,IPC,MSTP,PSCU (secure/nonsecure). 1196 register records/4271 fields;347 unmatched/859 fields, of which2 ICU records/64 fields are stale-SVD false gaps and4 FCACHE.FSAR/SYSC.FWEPROR alias records/12 fields lack current KF corroboration. Remaining341 records/783 fields are alleged omissions, plus named/manual-only gaps HDR-C01–09; MWMCR deduplicates HDR-A02. SVD compact cache lacks dimensions/increments/reset masks: exhaustive expanded-array/reset certification is NOT established. HM/TU takes precedence for PCKE,SCKDIVCR2,RSCSAR,CPU monitors,DSLPWUPIRQEN2(+218 vs stale+21C); TU2026-02-06 corrects MIPIC/NPU MPU end reset bits. PVD4/5 offset remains contradictory, not a resolved constant.

### ICU primary-source review returned

Task_mwkdnp34_76dbb9 reviewed complete C/instance/API/MDF including five APIs,ISR,all checking/LOCO/filter/callback/NSC/default/event/pin branches. ICU_COMMON selection agrees with HM/TU; five inherited defects/gaps recorded separately. SVD erroneous IRQCR enum16/17 yields to HM2/3; KF CPU1 applicability from HM1.4. Exclusive cross-core/channel ownership and hardware remain unverified.

### Graphics/connectivity exact primary-inventory coverage

Task_mwkd86pu_7e5992 covered USBFS/HS,GLCDC,DRW,MIPI_DSI,MIPI_PHY0,CEU,CANFD0/1,PORT0–D,PFS,MIPI_CSI0,VIN0,ECCMB0/1,MFWD,ESWM,COMA,RMAC0/1,GWCA0,GPTP (secure/NS) and ETHA0_NS/1_NS. Total72/3268/15796 peripheral/register/field records. Missing24 aliases represent1452 register/4422 field records, not passing entries. GPTP deduplicates HDR-T01. NPU and secure ETHA0/1 are manual-confirmed yet SVD-absent. 531 scalar views/1800 fields/3600 macros matched serialization only, not independent hardware correctness. Reset values present in3268 SVD records were not preserved by schema; complete reset qualification unestablished. USB DPUSR2R TU correction, KF16-buffer CANFD limits and DRW.LVSTARTI32-bit manual definition override stale SVD. Package-reserved PORT/PFS and gamma slots are not access permission.

### Test-review continuation boundaries

Fresh numerical/driver-test continuation task_mwkdtuio_c4bcc2 owns full aux/aux-peripherals/bus/CANFD/display/GLCDC/graphics/LPM/DSI/OSPI/SCI_SPI/timer tests; remaining device-header261–401,capabilities301–437,clocks301–542,metadata1–79; CGC harness1–339,565–729,WDT246–418,memory/analog361–671,startup_tcm and other layout/BSP fixtures. Fresh host-qualification continuation task_mwkdv87j_87535f owns: compatibility,legacy-negative,RTOS tests and helpers; candidate test1–339,440–1126; regression tests261–891; pack tests221–605 and resources251–446; compatibility.py1–183,364–417; regression.py261–400; stock_regression.py580–702; verify_candidate.py1–238,429–570,711–746 and MDF/resource helper oracle checks. Initial review neither ran mutations nor established complete independent numeric correctness.

### Older-device static accounting

Task_mwkdljbt_7af8c6 accounts96 tracked changed owners,32 existing MCU capability pairs,shared source/header/RTOS paths,RA8D1 BSP MDF,changed driver MDFs,assembly/capability preparation and pack ownership. Original capability values intact and1013 existing MDFs equal original archive per reviewer. OLD-001 is the sole alleged older-configuration change. No compile/generation/object/runtime verification was performed during this review; target-only and harness correctness excluded.

### ADC_B initial review returned

Fresh reviewer task_mwkd69bx_33bedb inspected all14 public APIs,13 API-table entries,28 ISRs, complete instance/API headers and MDF. ADC-001–012 recorded (9 High/3 Medium) before fixes. Inherited defects included as allegations, not approved older-device changes. Remaining scope explicitly includes InfoGet DMA description, compare/fixed-channel support, S&H ordering/mode, differential/shared-source restrictions and compiler treatment of nonvolatile FIFO casts; bounded continuation requested. HM54/70, supplied SVD1.10.02 and applicable TUs compared; AD/KF ADC16H correspondence checked via HM1.15. Runtime remains unverified.

### SCI_B SPI initial review returned

Fresh reviewer task_mwkdqz2b_40b1ad covered4 files/1883 physical lines, all17 functions (7 public/6 helpers/4 ISRs),27 register-access sites/11 registers, checking/DTC branches, TrustZone callbacks,7 secure guards/NS wrapper,17 MDF properties/12 constraints. SCISPI-001–004 recorded; reviewer reports inherited original5.9 issues; SCKSEL capability delta itself found consistent. Timing, generated secure linkage, dual-core/DTC runtime remain unverified.

### Board/configurator/pack initial review returned; continuation required

Fresh reviewer task_mwkdl3g9_01f369 covered both authoring tools,5 shared MDF diffs,9 new MDF/config structures,5 board files,439 pin settings/112 symbolic names,33 packaged pin-model copies,3 PDSCs/3 tooling files and listed device/debug/linker assets.74 generated configs surveyed/7 pin variants/10 clock variants; representative outputs inspected only. CFG-001–003 recorded. Earlier apparent source change was reviewer file confusion, retracted by reviewer. Detailed large FSP/device enum/security/option correspondence and debugger/bootloader branches remain incomplete; no exhaustive pass.

### Primary-inventory reconciliation and queued review

The four header assignment counts total250 SVD peripheral records and overlap both GPTP aliases, leaving9 distinct records not yet assigned: ELC/ELC_NS,FACI,DOTF0/DOTF1 and their NS aliases,PDG/PDG_NS. A fresh review of those9 plus generic generator emission/collision/overlap logic is queued: launch was refused at11 active agents against limit10. No duplicate agent was started. Numerical test continuation task_mwkdtuio_c4bcc2 and qualification continuation task_mwkdv87j_87535f remain read-only.

ADC reviewer clarification adds zero findings: InfoGet DMA/compare/fixed-channel absence was not proved a contract defect; broader S&H/differential restrictions and nonvolatile FIFO concern were coverage gaps, not additional confirmed allegations. Bounded read-only continuation is checking those gaps. Core/header reset and missing-NPU facts remain evidence limitations, not automatic requests to implement unsupported drivers.

### LPM and GLCDC initial review returned

LPM task_mwkdpnk4_3784ed covered all5 APIs/6 helpers, all exposed modes, checking/standby-limit branches, oscillator/protection/retention/MDF/NSC paths.10 allegations (5High/5Medium). CPDLPSTATE/cache/multicore runtime remain qualification gaps; SVD wake-offset conflict retained. GLCDC task_mwkdqz2t_12815e covered11 APIs,28 helpers,3 ISRs,both headers,173 properties/140 constraints.10 reported groups split into14 independently repairable allegations GLCDC-001–014. Gamma single-switch adaptation/unity curves found consistent; inheritance does not itself approve behavior on target. Security attribution/concurrency/physical output unverified.

Remaining-header review returned from fresh task_mwkdzfys_bc4922: all9 remaining SVD records plus generator emission/collision/core selection. ELC(18 records/134 fields across aliases) matches represented facts; FACI(2/4) correctly excluded for KF; DOTF(8/8) and PDG(12/30) omitted. HDR-R01–03 record omissions and two latent generator guards. DOTF CONVAREAD reset conflict retained (SVD0 versus HM0x00000FFF); expanded-array/reset completeness is not asserted. No other block families duplicated.

### Qualification-test continuation returned

Fresh task_mwkdv87j_87535f reviewed all assigned ranges and supporting helpers. Six reports: five new TEST-005–009 plus truncated-vector duplicate attached to TEST-003. All are static predicted escapes, not executed mutations. Remaining qualification gaps explicitly include RTOS compiler/core identity/completeness, source-to-ELF freshness,writable-data parity and required IRQ mapping. Resource-helper tests reuse own contracts rather than independently checking published resources. No test/build/edit/hardware operation occurred.

### RTOS and clock initial reviews returned

FreeRTOS8allegations and ThreadX4allegations recorded; entire assigned non-IARports and dependencies read. Noexecutionorbuild. BSPclock reviewer14initialfindings maptoCLK-001–013plusduplicateBSP-005.98nodes/29constraints/2567optionsinventoriedbutnotallproven; numerical-options/voltage-matrixcontinuationrunning. Corrected subjectsystem.c pathisCMSISDeviceSource,notmcu/all/system.c. Fresh BSPcapability/support-header review task_mwke11yw_aa8882nowrunning; not overlappingclockalgorithms.

### Numerical-test continuation returned

Task_mwkdtuio_c4bcc2 covered 82 methods across 14 full test files, 22 methods in four ranges, and assigned C fixtures. Four reports: duplicate numeric oracle under TEST-001 plus TEST-010–012. Static counterexamples only; no mutations run. All reviewed tests remain evidence of limited specified properties, not complete hardware truth.

### ADC and graphics-header continuations closed

ADC task_mwkd69bx_33bedb returned six additional initial allegations ADC-013–018 (four Medium, two High): S&H ordering/occupancy/mode, differential input admissibility, co-started shared sources, and nonvolatile FIFO source access. No emitted-instruction or hardware failure is claimed; source validation paths were traced. Optional unimplemented S&H controls and InfoGet DMA description were not proven contract findings.

Graphics/header task_mwkd86pu_7e5992 closed represented-field/reset inspection. HDR-G16 now enumerates 39 existing raw registers/93 missing fields per alias against HM64.2.30–42. SRC-001 retains 26 cached PFS narrow-view reset discrepancies; supplied evidence is not silently rewritten. No consumer of cached resetValue or unchecked startup reset dependency was identified. Missing C reset macros alone are not a defect. NPU register count and instantiated revision remain unknown pending matching Arm Ethos-U55 TRM/configuration evidence; known bases do not establish its register map. CANFD word-access permissibility remains unresolved, distinct from the documented register-width mismatch.

### Metadata and capability continuations returned

CFG-004–006 record three independently fixable metadata allegations from task_mwkdl3g9_01f369. Device inventory256enums/341options/226provides/1property; FSP inventory150properties/990options/585enums/5127options. Counts are structural only; ADC407enum families, security templates1378–1687, BPS/PBPS/FSBL validity, crypto2560–2684 and debugger resolution retain explicit semantic gaps. Security and ADC metadata fresh bounded reviewers are already running; no duplicate launched.

CAP-001–002 record capability allegations from fresh task_mwke11yw_aa8882. All four headers read:512feature definitions/189peripheral definitions/207explicit enum values; shared fsp_features,ioport,clocks,module_stop,sdram changes also read. This is not908individually verified facts: complete per-value source dispositions/TU applicability/shared masks remain open. AD single-core/no-MIPI/512KB versus KF dual-core/MIPI/1MB applicability must be preserved.

### MIPI DSI initial review returned

Fresh task_mwkdrquw_c4ca1f reviewed28/28functions(8APIs/14helpers/6ISRs),bothheaders,55MDFproperties/39constraints/11exports/61options/6interrupts;49register names/718SVDposition-maskdefinitions. DSI-001–011recorded. Six added status-clear guards matched hardware; allegations concern inherited/unadapted paths. No builds/test/e2/hardware. AD-labelled SVD confirms layout only;fittedKF MIPI presence uses datasheet1.3. DisabledIRQ generation/fullPHYtiming/fault-reset races/coreownership remain explicitqualificationgaps.

### Clock numerical/voltage continuation closed

Task_mwkdbd0r_25ccb4 statically evaluated local formulas/encodings across2567options/98nodes:1353match,1214invalidunion(1040decimal-third mismatches,346reportedpackingtruncations,172overlap);33exports enumerated and1694ratio evaluations locally consistent. These are source arithmetic evaluations,not builds or full-configuration/IDEvalidation. Decimal-thirds duplicate CLK-010;new CLK-014–016 cover GPT3/5 restriction,missinglegaldivisors,andlowVCC limits. Packing allegation exactlocation clarificationrequested. KFLCACgroupA:VSCR1CPU0/CPU1/NPU/ICLKmax1000/250/500/250MHz;VSCR2max600/150/300/150MHz(datasheet2.49). Noexhaustive transition interleavings/recovery/hardware qualification. SPI/OCTA333.33HMvs333datasheet discrepancy retained;stricterguaranteedlimitnot silently relaxed.

### Fresh ADC enum semantics continuation closed

Task_mwke63s1_78eeff reviewed407enums/4182options inBSP3221–8216 (37instances*11families;virtual33–36 correctlygroupNoneonly) plus11enums/260options at2939–3220. Numeric encodings match citedHM54/70;minimumphase duplicateADC-004;twoadditionalconsumerdefectsADC-019–020recorded. Repeatedfamilyuniformitynotindependentproof. Noencodingfactremainssourceblocked;laterliveconfiguratorsubstitutionrequiresverification. Noedits/executablechecks.

### Fresh security-option metadata review closed

Task_mwke63s5_8a07ad coveredcomplete1378–1687securitytemplate,allBPS0–15/PBPS0–3bitmaps,FSBLexpressions,cryptoenums2560–2684,sources/packcopies/debuggerPG/GDB/zoneidentity. ProtectionduplicateattachedBSP-001;SEC-001–007 preserveFSBLandremainingallegations separately. StaticKFdualcoredebugidentityconsistent;stepping/emittedprogrammingartifacts/crypto-library/runtimeunverified. Noedits/test/build/e2/hardware.

## Initial-review report barrier closed; no exhaustive sign-off

All assigned initial and bounded-continuation reports have returned. All initial allegations are recorded before any production,metadata,generator,or testfix. The parent may now independently adjudicate each allegation. This closes report collection only,not all requested hardware-semantic coverage. Remaining gaps stay qualification blockers: missingmatchingEthosU55configuration/TRM; compactSVDdimension/resetmasklimits;26uncertainperipheralmacroentries;508valuedfeature/207overrideentrieswithoutcompleteper-value disposition; exhaustiveclocktransition/recoveryinterleavings;configuration/optionalIRQ/securitygeneratedoutputandphysicalruntime. No missing scope is called a pass.

Task_mwke11yw_aa8882continuation:161/189peripheralmacros source-supported(83presence/masks,78absentlegacyforms),2contradictedECCMBentries(CAP-003),26uncertain. Exactuncertainfamilies:ACMP,ACMPHS_B,AMI,ANALOG,DPHYCNT,DSILINK,ECCAFL,ELC_B,FACI,FCACHE,FLAD,IIC_B,IIC0WU_B,IRTC,MRMS,MRRGE,PFS_B,PMISC,PORGA,SPMON,SRCRAM,SSI_COMMON,andUSB_CHANNEL_MASK. SystemWUPEN/DPSIER/DPSIEGR/percoreDMA-DTC/ADCstopmaskssupported;otherstopformulasnotcleared. IntermediateGPT/PDGstopconcernwasnotdeliveredasevidencedfindingandremainsunresolvedcoverage,notaconfirmeddefect.

Freeze integrity immediately before barrier:4473/4473initial input hashes match;0changed/missing/unsupportedrecords. Subsequent fixes must preserve snapshot references and use new evidence revisions.

## Primary-source adjudication checkpoint

All 228 initial IDs now have a disposition: **224 Confirmed (including narrowed expectations), 1 Rejected, 3 Unresolved**. This is not a repaired/qualified count. DUAL-003 is rejected only for the recorded GNU13.2.1/current generated CPU1 flags: parent inspected the actual two-store finite scrub loop and later initialization relocations against HM2.17.1.1 Table2.37 pp191–192. Six optimization levels and negative instruction controls are retained in `evidence/tcm-codegen/`; other compilers/LTO and physical boot remain unqualified. Unresolved IDs: HDR-C06 (PVD4/5 offsets), HDR-G15 (matching NPU register specification), SRC-001 (26 narrow-view reset/source discrepancies, no candidate reset consumer established).

Repairs are in progress in disjoint owning files. Delivered focused tests are not final integration evidence. Header integration, target MDF/security/clock constraints, independent-oracle repairs, MRAM recovery/coherency, BSP clock transitions and RTOS repairs must converge before immutable publication. Existing installed/generated r014 artifacts remain historical; no new hardware operation is authorized. Every original coverage limitation above remains unless a specific later evidence record closes it.

## Repaired-candidate checkpoints and supplemental review

- r015 was built from 4,309 stable owning inputs (`evidence/r015-owning-inputs.json`), with37 candidate archives and33 supplied target pin-model copies verified byte-for-byte (`r015-archive-delta-and-pins.json`). Installed only into the authorized isolated support area; journal plan433fc5. No hardware access.
- All23 changed/new owning MDFs passed live schema/reference validation with the canary (`repaired-metadata-validation-corrected.log`). The initial run caught a DSI constraint placed after properties; it was moved to the schema-permitted module-constraint region. An omitted I3C restriction capability was provided. The failed initial log is retained, not relabeled as a pass.
- Fresh Minimal CPU0 and CPU1 templates preserve per-image warm hooks and now exclude CPU1 from default shared pin/SDRAM setup. Both linked and clean-built. `r015-bsp-source-elf-final.json` verifies3692 owning sources, actual CM85/CM33 flags/debugger/vector/stack/option ownership and disjoint physical PT_LOAD ranges. The CLI generic generated-region overlap warning is not an actual ELF overlap. Explicitly cleaning CPU0 left a fresh Smart Bundle but no ELF, so the parent rebuilt CPU0 then CPU1; all failure/recovery logs remain.
- Fresh default MRAM/DAC_B/PDM/WDT/CGC instances link on both cores through standard interfaces. MRAM emits a disclosed RWX LOAD warning for RAM-resident code. ADC's untouched stack correctly exposes clock prerequisites: raw default produced3 unique clock/timing violations (CLI count6 includes duplicate details). A configuration-only48MHz HOCO/system/PCLKA/ADCCLK recipe clears them; CPU1 uses a dedicated CPU0 clock-owner predecessor with no competing ADC instance. This is compile/configuration evidence, not analog or clock measurement.
- Supplemental CLK-018 was recorded before repair: the legal dedicated-divider encoding9 was decoded as16 rather than32. Type6-only correction and32-device legacy helper parity passed.
- After GPT/OSPI became changed owners, fresh read-only reviewers `task_mwkjp5g2_e2d27b` and `task_mwkjp5ck_c2e78a` reviewed those drivers against primary sources, without author notes/tests. PDG-001 and OSPI-001..007 were recorded before their repairs and independently adjudicated by the parent. PDG readback and normal-OSPI repairs are for r016, not claims about r015. OSPI source-introduction status for inherited NULL/alignment defects was established by the parent's original nested HEAD comparison. DOTF remains source/crypto-binding blocked; no private register or key mapping may be invented.

The ledger now contains228 initial findings plus9 supplemental findings (237 total). Current source/metadata follow-up, final r016 publication, complete host suite, stock-module census and fresh older-device/RTOS generated regressions remain pending. No checkpoint is an exhaustive sign-off.

## Final r018 scoped software closure

This section supersedes the pending-work wording of earlier chronological checkpoints only where the specific evidence below applies. It does not erase initial uncovered scope or establish exhaustive device qualification.

- Final ledger: **242 IDs**, comprising 228 initial and 14 supplemental findings, all recorded before their respective fixes. **238 Confirmed, 1 Rejected, 3 Unresolved; 229 repaired within their stated software scope, 12 Open, 1 Rejected.** Per-area/severity counts and the current ledger hash are in [`evidence/findings-status-final.json`](evidence/findings-status-final.json). Every row retains its allegation/adjudication/source and now links final applicable verification and physical limitations.
- Immutable r018 manifest SHA-256: `eb4dd36f99fb67c1692f7b56d5439c312381e8a4897dfbb30711b9ef491d3960`. All **37 archives and every entry** were rehashed; all **33 supplied pin-model payloads** match packaged bytes. All **4,389 production/MDF/test inputs** remain equal to the full-suite snapshot. See [`final-r018-freeze-identity.json`](evidence/final-r018-freeze-identity.json). No original release, prior revision, supplied SVD or pin model was rewritten.
- **889 host tests pass**, no failures/errors/skips, using the complete pinned GNU 13.2.1 compiler. [`Full log`](evidence/final-r018-host-tests.log), [`stable-input proof`](evidence/final-r018-host-tests-input-proof.json). Independent-primary-oracle/mutation controls are bounded assertions, not every-value certification.
- Fresh r018 CPU0 and CPU0→CPU1 Minimal clean builds and full source/ELF checks pass. Actual compiler/core/debugger, vector/reset/stack, CPU0 option ownership, TCM aliases and **allocated physical** image/RAM disjointness are checked. Generic CLI generated-region overlap warnings are retained; actual ELF checks are not replaced by that generic description.
- **24 fresh driver-mode clean links and 24 source/ELF cases** pass: MRAM, DAC_B, PDM, WDT, ADC_B, CGC × both cores × parameter checking on/off. Every mode's artifacts/configuration are archived and rehashed. A final audit found that old r014 untouched-default evidence could not transfer across changed inputs; **6 additional uncustomized-default clean links**, **3 source/ELF pairs** and **6 layer checks** were therefore run freshly for MRAM/DAC_B/PDM at r018. No property/BSP/spec overrides or application edits were used for these six new default projects. See [`matrix`](evidence/r018-parent-driver-matrix.json), [`build/archive proof`](evidence/final-r018-parent-build-proof.json), [`untouched defaults`](evidence/final-r018-untouched-defaults.json).
- Both-core r018 board check passes with **551 settings/0 unknown pin IDs**, zero warnings/errors/configurator problems. All **23 changed/new MDF inputs** pass live schema/reference validation with **canary reported**. Supplied-model component alternatives/informational warnings remain explicitly disclosed, not treated as pin-model defects. [`Board log`](evidence/r018-board-check.log), [`MDF log`](evidence/final-r018-metadata-validation.log).
- Expanded HAL owner actually regenerated **42 existing projects** at r018 and verified unchanged compiled inputs/artifacts, preserving 38 r016 and 4 r017 link origins; **21 existing pairs** pass current source/physical-ELF checks. New CRC SCI8 TDR/RDR and comparator0/1 controls add **4 fresh clean links/8 active pristine-candidate TU results**. PVD menus preserve default6 and exclude illegal0–2. The **152-row census is r017 source compilation transferred through actual unchanged-input proof**, not freshly recompiled r018. Raw module statuses are 53 candidate passes/0 failures/18 blocked/33 absent/48 variant mismatches; complete active-TU coverage is separately qualified. Three partial/compiler-dependent rows, **14 inactive/excluded TUs per core**, five separate zero-source integrations and BL2/TF-M prerequisites remain visible.
- USB/security owner actually regenerated **38 models**: **4 fresh default clean links** plus **34 r016 transfers**, and **19 current source/ELF pair passes**. Six optional USB/PSA paths remain inactive; 96 fresh build TUs plus8 active pristine/adapted source cases are separately counted. RTOS owner actually regenerated **4 current models**, with **0 fresh links/target TU compiles**; exact inputs retain r016-via-r017 **24 links,204 candidate+204 pristine port TU passes,4560 dependency scans**. All **12 archived+2 current pairs** pass current source/ELF inspection. Scheduler/FP/tick/NS runtime is not qualified.
- Older-device canonical regression passes **18 fixture rows** and retains **262 TU/configuration parity comparisons over38 changed shared TUs**: 4 rows/74 comparisons originate r017,14 rows/188 comparisons r016; **0 new r018 links/comparisons**. Current actual owners/generated inputs/artifacts and legacy metadata were rechecked for unchanged applicability. Six MCU controls (RA8M1,RA6T2,RA8D1,RA4M2,RA4M1,RA0E1), checking on/off and six RTOS controls are retained. No required shared TU/control/RTOS-option gap remains in that bounded report. This is not older-device runtime evidence.
- Final detailed outcomes, literal build/artifact/pack lines, intentional target-only corrections and all12 open IDs are in [`evidence/final-r018-summary.md`](evidence/final-r018-summary.md). The mandatory before/after header/API table is [`evidence/final-compatibility.md`](evidence/final-compatibility.md). Cross-owner aggregation is a separate hash-bound readiness check, not permission to relabel transfers as fresh.

**Coverage remains incomplete.** Missing/conflicting primary facts (GPTP PTPSCR, PVD4/5, MFWD dimensions, ESWM TPEMIMC0, GWIDC address, configured Ethos-U55, PFS resets), exact irreversible MRAM timing, DOTF crypto binding, Secure/Nonsecure partitions/routing, ThreadX selected-core MDF timing and all original per-value/optional/interleaving gaps remain open. Nineteen older custom CPU1 warm hooks were preserved, not silently migrated to the new template. No hardware discovery, probing, flashing, serial, debugger, reset, capture or security programming was performed; physical behavior remains unverified.
