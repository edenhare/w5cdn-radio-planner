"""Tri-state tests for Hardware Exporters (CHIRP, RT Systems, Generic)."""

import csv
import io
from pathlib import Path

from core.exporters import export_codeplug, get_exporter
from core.exporters.chirp import CHIRP_COLUMNS
from core.managers.radio_manager import RadioManager
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug


def create_sample_codeplug() -> Codeplug:
    """Helper to create sample codeplug."""
    ch1 = RadioChannel(
        number=1,
        name="TYLER 146.94",
        callsign="W5ETX",
        rxFreq=146.94000,
        txFreq=146.34000,
        offset=0.60000,
        offsetDir="-",
        mode="FM",
        toneMode="Tone",
        ctcss="136.5",
        city="Tyler",
        state="TX",
        comment="Tyler RPT",
    )
    ch2 = RadioChannel(
        number=2,
        name="2m CALL",
        rxFreq=146.52000,
        txFreq=146.52000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        toneMode="None",
        comment="National Simplex",
    )
    return Codeplug(name="SampleCodeplug", channels=[ch1, ch2])


def test_chirp_exporter_format_and_columns():
    """Good Data: Verify CHIRP exporter generates exactly 21 columns with compliant header."""
    cp = create_sample_codeplug()
    mgr = RadioManager()
    spec = mgr.get_radio("btech_dmr6x2")

    exporter = get_exporter("CHIRP")
    csv_text = exporter.to_csv_string(cp, spec)

    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # 1 header + 2 channel rows
    assert len(rows) == 3
    assert rows[0] == CHIRP_COLUMNS
    assert len(rows[0]) == 21

    # Check first channel row against official CHIRP CSV_FORMAT
    ch1_row = rows[1]
    assert ch1_row[0] == "1"  # Location
    assert ch1_row[1] == "TYLER 146.94"  # Name
    assert ch1_row[2] == "146.940000"  # Frequency
    assert ch1_row[3] == "-"  # Duplex
    assert ch1_row[4] == "0.600000"  # Offset
    assert ch1_row[5] == "Tone"  # Tone
    assert ch1_row[6] == "136.5"  # rToneFreq
    assert ch1_row[7] == "88.5"  # cToneFreq
    assert ch1_row[8] == "023"  # DtcsCode
    assert ch1_row[9] == "NN"  # DtcsPolarity
    assert ch1_row[10] == "023"  # RxDtcsCode
    assert ch1_row[11] == "Tone->Tone"  # CrossMode
    assert ch1_row[12] == "FM"  # Mode
    assert ch1_row[13] == "5.00"  # TStep
    assert ch1_row[14] == ""  # Skip
    assert ch1_row[15] == "50W"  # Power
    assert ch1_row[16] == "Tyler RPT"  # Comment
    assert ch1_row[17:21] == ["", "", "", ""]  # URCALL, RPT1CALL, RPT2CALL, DVCODE


def test_anytone_at778uv_chirp_export():
    """Verify AnyTone AT-778UV CHIRP export enforces 5-char LCD limit and 21 CHIRP columns."""
    cp = create_sample_codeplug()
    mgr = RadioManager()
    spec = mgr.get_radio("anytone_at778uv")

    exporter = get_exporter(spec.programmerType)
    csv_text = exporter.to_csv_string(cp, spec)

    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    assert len(rows) == 3
    assert rows[0] == CHIRP_COLUMNS
    assert rows[1][0] == "0"
    assert rows[2][0] == "1"
    for data_row in rows[1:]:
        assert len(data_row[1]) <= 5


def test_chirp_exporter_sanitizes_restricted_and_dcs_tones():
    """Verify CHIRP exporter never emits non-float rToneFreq/cToneFreq when ctcss is 'Restricted' or 'D205'."""
    ch_restricted = RadioChannel(
        number=1,
        name="Beckl",
        rxFreq=147.36,
        txFreq=147.96,
        offset=0.6,
        offsetDir="+",
        mode="FM",
        toneMode="Tone",
        ctcss="Restricted",
    )
    ch_dcs_in_pl = RadioChannel(
        number=2,
        name="Oneon",
        rxFreq=147.375,
        txFreq=147.975,
        offset=0.6,
        offsetDir="+",
        mode="FM",
        toneMode="Tone",
        ctcss="D205",
    )
    cp = Codeplug(name="SanitizeTest", channels=[ch_restricted, ch_dcs_in_pl])
    mgr = RadioManager()
    spec = mgr.get_radio("anytone_at778uv")

    exporter = get_exporter("CHIRP")
    csv_text = exporter.to_csv_string(cp, spec)
    rows = list(csv.reader(io.StringIO(csv_text)))

    # Row 1 ('Restricted'): Tone cleared to '', rToneFreq and cToneFreq are valid floats ('88.5')
    assert rows[1][5] == ""
    assert float(rows[1][6]) == 88.5
    assert float(rows[1][7]) == 88.5

    # Row 2 ('D205'): Converted to DTCS with DtcsCode '205' and valid float rToneFreq ('88.5')
    assert rows[2][5] == "DTCS"
    assert float(rows[2][6]) == 88.5
    assert rows[2][8] == "205"
    assert rows[2][10] == "205"


def test_rt_systems_exporters():
    """Good Data: Test RT Systems exporters for BTECH, Wouxun, Baofeng, Alinco."""
    cp = create_sample_codeplug()
    mgr = RadioManager()

    radios_to_test = [
        ("btech_dmr6x2", "RT_SYSTEMS"),
        ("wouxun_kg_uv980p", "RT_SYSTEMS"),
        ("baofeng_5rm", "RT_SYSTEMS"),
        ("baofeng_uv5g_plus", "RT_SYSTEMS"),
        ("alinco_dr735t", "RT_SYSTEMS"),
    ]

    for radio_id, prog_type in radios_to_test:
        spec = mgr.get_radio(radio_id)
        exporter = get_exporter(prog_type)
        csv_text = exporter.to_csv_string(cp, spec)

        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        assert len(rows) >= 2
        # Header must match spec columns
        assert rows[0] == spec.columns
        # Number of columns in data rows must match header length
        for data_row in rows[1:]:
            assert len(data_row) == len(spec.columns)


def test_exporter_clamping_to_max_channels():
    """Bad / Edge Data: Codeplug exceeding maxChannels is clamped."""
    mgr = RadioManager()
    spec = mgr.get_radio("baofeng_5rm").model_copy(update={"maxChannels": 2})

    channels = [RadioChannel(number=i, name=f"CH{i}", rxFreq=146.52, txFreq=146.52) for i in range(1, 10)]
    cp = Codeplug(name="LargeCodeplug", channels=channels)

    exporter = get_exporter("CHIRP")
    csv_text = exporter.to_csv_string(cp, spec)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # 1 header + 2 clamped channels
    assert len(rows) == 3


def test_export_to_file(tmp_path: Path):
    """Test exporting codeplug to file on disk."""
    cp = create_sample_codeplug()
    mgr = RadioManager()
    spec = mgr.get_radio("baofeng_5rm")

    out_file = tmp_path / "exports" / "test_out.csv"
    res = export_codeplug(cp, spec, out_file, programmer_type="CHIRP")
    assert res.is_file()
    assert res.stat().st_size > 0
