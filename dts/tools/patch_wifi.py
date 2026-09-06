#!/usr/bin/env python3
"""Patch the decompiled zorn DTS to enable PCIe0 + WCN7850 WiFi.

Everything is expressed with numeric phandles because the DTS came from a DTB
(no labels survive decompilation).
"""
import re
import sys

SRC = 'v26.dts'
DST = 'v29.dts'

# phandles that already exist in the DTB
PH_L15B = '0xc1'   # vreg_l15b_1p8  -> vddio
PH_L3C  = '0xc2'   # vreg_l3c_1p2   -> vddio1p2
PH_S3C  = '0x11a'  # vreg_s3c_0p9   -> vdddig
PH_S1C  = '0x117'  # vreg_s1c_1p2   -> vddrfa1p2
PH_S6C  = '0x118'  # vreg_s6c_1p8   -> vddrfa1p8
PH_RPMHCC = '0x02'
RPMH_RF_CLK1 = '0x06'

# new phandles (DTB max was 0x141)
PH_S4I  = '0x142'  # vreg_s4i_0p85  -> vdd        (node smps4, had no phandle)
PH_S2C  = '0x143'  # vreg_s2c_0p8   -> vddaon     (node smps2, had no phandle)
PMU_REGS = [
    ('ldo0', 'vreg_pmu_rfa_cmn',   '0x144'),
    ('ldo1', 'vreg_pmu_aon_0p59',  '0x145'),
    ('ldo2', 'vreg_pmu_wlcx_0p8',  '0x146'),
    ('ldo3', 'vreg_pmu_wlmx_0p85', '0x147'),
    ('ldo4', 'vreg_pmu_btcmx_0p85','0x148'),
    ('ldo5', 'vreg_pmu_rfa_0p8',   '0x149'),
    ('ldo6', 'vreg_pmu_rfa_1p2',   '0x14a'),
    ('ldo7', 'vreg_pmu_rfa_1p8',   '0x14b'),
    ('ldo8', 'vreg_pmu_pcie_0p9',  '0x14c'),
    ('ldo9', 'vreg_pmu_pcie_1p8',  '0x14d'),
]
PMU = {n: p for _, n, p in PMU_REGS}

src = open(SRC).read()
lines = src.split('\n')


def fail(msg):
    print('PATCH FAILED: ' + msg)
    sys.exit(1)


def node_span(startline):
    """Return (start_idx, end_idx) of the node whose opening brace is at startline."""
    depth = 0
    for i in range(startline, len(lines)):
        s = lines[i].strip()
        if s.endswith('{'):
            depth += 1
        elif s == '};':
            depth -= 1
            if depth == 0:
                return startline, i
    fail('unterminated node at line %d' % startline)


def find_node(pattern):
    for i, ln in enumerate(lines):
        if re.match(pattern, ln):
            return i
    return None


def set_status_okay(nodeline, what):
    a, b = node_span(nodeline)
    for i in range(a, b + 1):
        if re.match(r'^\t+status = "disabled";$', lines[i]):
            ind = len(lines[i]) - len(lines[i].lstrip('\t'))
            lines[i] = '\t' * ind + 'status = "okay";'
            print('  %-26s status -> okay (line %d)' % (what, i + 1))
            return
    fail('no disabled status inside ' + what)


def add_phandle(nodeline, ph, what):
    a, b = node_span(nodeline)
    for i in range(a, b + 1):
        if 'phandle = <' in lines[i]:
            fail(what + ' already has a phandle')
    ind = len(lines[a]) - len(lines[a].lstrip('\t')) + 1
    lines.insert(b, '\t' * ind + 'phandle = <%s>;' % ph)
    print('  %-26s phandle = %s' % (what, ph))


def find_regulator_node(name):
    """Line index of the opening brace of the node carrying regulator-name = name."""
    for i, ln in enumerate(lines):
        if re.search(r'regulator-name = "%s";' % re.escape(name), ln):
            d = len(ln) - len(ln.lstrip('\t'))
            for j in range(i, -1, -1):
                c = lines[j]
                ci = len(c) - len(c.lstrip('\t'))
                if c.rstrip().endswith('{') and ci < d:
                    return j
    fail('regulator %s not found' % name)


print('=== 1. enable PCIe0 controller and PHY ===')
set_status_okay(find_node(r'^\t\tpcie@1c00000 \{'), 'pcie@1c00000')
set_status_okay(find_node(r'^\t\tphy@1c06000 \{'), 'phy@1c06000')

print('=== 2. give vreg_s4i_0p85 / vreg_s2c_0p8 phandles ===')
add_phandle(find_regulator_node('vreg_s4i_0p85'), PH_S4I, 'vreg_s4i_0p85 (smps4)')
add_phandle(find_regulator_node('vreg_s2c_0p8'), PH_S2C, 'vreg_s2c_0p8 (smps2)')

print('=== 3. add wifi@0 under pcie@1c00000/pcie@0 ===')
rp = find_node(r'^\t\t\tpcie@0 \{')
if rp is None:
    fail('root port pcie@0 not found')
a, b = node_span(rp)
wifi = [
    '\t\t\t\twifi@0 {',
    '\t\t\t\t\tcompatible = "pci17cb,1107";',
    '\t\t\t\t\treg = <0x10000 0x00 0x00 0x00 0x00>;',
    '\t\t\t\t\tvddrfacmn-supply = <%s>;' % PMU['vreg_pmu_rfa_cmn'],
    '\t\t\t\t\tvddaon-supply = <%s>;' % PMU['vreg_pmu_aon_0p59'],
    '\t\t\t\t\tvddwlcx-supply = <%s>;' % PMU['vreg_pmu_wlcx_0p8'],
    '\t\t\t\t\tvddwlmx-supply = <%s>;' % PMU['vreg_pmu_wlmx_0p85'],
    '\t\t\t\t\tvddrfa0p8-supply = <%s>;' % PMU['vreg_pmu_rfa_0p8'],
    '\t\t\t\t\tvddrfa1p2-supply = <%s>;' % PMU['vreg_pmu_rfa_1p2'],
    '\t\t\t\t\tvddrfa1p8-supply = <%s>;' % PMU['vreg_pmu_rfa_1p8'],
    '\t\t\t\t\tvddpcie0p9-supply = <%s>;' % PMU['vreg_pmu_pcie_0p9'],
    '\t\t\t\t\tvddpcie1p8-supply = <%s>;' % PMU['vreg_pmu_pcie_1p8'],
    '\t\t\t\t};',
]
lines[b:b] = wifi
print('  wifi@0 inserted at line %d (%d lines)' % (b + 1, len(wifi)))

print('=== 4. add wcn7850-pmu at root ===')
pmu = [
    '',
    '\twcn7850-pmu {',
    '\t\tcompatible = "qcom,wcn7850-pmu";',
    '\t\twlan-enable-gpios = <0x92 0x10 0x00>;',
    '\t\tbt-enable-gpios = <0x92 0x11 0x00>;',
    '\t\tvdd-supply = <%s>;' % PH_S4I,
    '\t\tvddio-supply = <%s>;' % PH_L15B,
    '\t\tvddio1p2-supply = <%s>;' % PH_L3C,
    '\t\tvddaon-supply = <%s>;' % PH_S2C,
    '\t\tvdddig-supply = <%s>;' % PH_S3C,
    '\t\tvddrfa1p2-supply = <%s>;' % PH_S1C,
    '\t\tvddrfa1p8-supply = <%s>;' % PH_S6C,
    '\t\tclocks = <%s %s>;' % (PH_RPMHCC, RPMH_RF_CLK1),
    '',
    '\t\tregulators {',
]
for node, name, ph in PMU_REGS:
    pmu += [
        '\t\t\t%s {' % node,
        '\t\t\t\tregulator-name = "%s";' % name,
        '\t\t\t\tphandle = <%s>;' % ph,
        '\t\t\t};',
    ]
pmu += ['\t\t};', '\t};']
# insert before the final closing brace of the root node
for i in range(len(lines) - 1, -1, -1):
    if lines[i].strip() == '};':
        lines[i:i] = pmu
        print('  wcn7850-pmu inserted at line %d (%d lines, 10 regulators)' % (i + 1, len(pmu)))
        break
else:
    fail('could not find root closing brace')

print('=== 5. unblock GPIO 16/17 (wlan/bt enable) and 94/96 (pcie perst/wake) ===')
pc = find_node(r'^\t\tpinctrl@f100000 \{')
a, b = node_span(pc)
for i in range(a, b + 1):
    if 'gpio-reserved-ranges' in lines[i]:
        ind = len(lines[i]) - len(lines[i].lstrip('\t'))
        # reserve 8..209 except {16,17,94,96}
        lines[i] = ('\t' * ind + 'gpio-reserved-ranges = '
                    '<0x08 0x08 0x12 0x4c 0x5f 0x01 0x61 0x71>;')
        print('  gpio-reserved-ranges -> 8..15, 18..93, 95, 97..209 (198 pins)')
        break
else:
    fail('gpio-reserved-ranges not found')

open(DST, 'w').write('\n'.join(lines))
print('\nwrote %s' % DST)
