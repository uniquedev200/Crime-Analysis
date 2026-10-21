"""Fictional Indian names and identity combinations for ATLAS Dev 3 synthetic data.

ALL NAMES, IDENTIFIERS, ADDRESSES, AND RELATIONSHIPS IN THIS FILE ARE
ENTIRELY FICTIONAL AND SYNTHETIC TEST DATA. NO REAL PERSONS OR RECORDS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SYNTHETIC_LABEL: Final[str] = "SYNTHETIC TEST DATA"


@dataclass(frozen=True)
class SyntheticPerson:
    """Fictional persona profile for synthetic test dataset generation."""

    name: str
    aliases: tuple[str, ...] = ()
    name_variants: tuple[str, ...] = ()
    father_name: str = ""
    age: int = 30
    gender: str = "Male"
    occupation: str = "Self-employed"
    address: str = ""
    phone: str = ""
    imei: str = ""
    vehicle: str = ""
    account: str = ""
    label: str = SYNTHETIC_LABEL


# ---------------------------------------------------------------------------
# Core Case A Personas (CASE-A-001)
# ---------------------------------------------------------------------------

VIKRAM_SINGH_A = SyntheticPerson(
    name="Vikram Singh",
    aliases=("Vicky",),
    name_variants=("Vikrum Singh", "Vikrama Singh"),
    father_name="Harbans Singh",
    age=32,
    gender="Male",
    occupation="Transport Contractor",
    address="House 45, Gali No 3, Laxmi Nagar, Delhi 110092",
    phone="+919876543210",
    imei="860123045678900",
    vehicle="DL01AB1234",
    account="001234567890",
)

RAJESH_SHARMA_A = SyntheticPerson(
    name="Rajesh Kumar Sharma",
    aliases=(),
    name_variants=("Rajesh Sharma",),
    father_name="Ramesh Sharma",
    age=45,
    gender="Male",
    occupation="Retail Merchant",
    address="Flat 102, Shanti Vihar, Rohini Sector 9, New Delhi 110085",
    phone="+919811122233",
    imei="860123045600011",
    vehicle="DL02CD5678",
    account="009876543210",
)

ARJUN_VERMA_A = SyntheticPerson(
    name="Arjun Verma",
    aliases=(),
    name_variants=(),
    father_name="Suresh Verma",
    age=28,
    gender="Male",
    occupation="Warehouse Supervisor",
    address="Plot 12, Phase 1, Okhla Industrial Area, New Delhi 110020",
    phone="+919822233344",
    imei="860123045600029",
    vehicle="UP16GH3456",
    account="005544332211",
)

# ---------------------------------------------------------------------------
# Core Case B Personas (CASE-B-002)
# ---------------------------------------------------------------------------

# Case B Vicky: same phone as Case A Vikram Singh, variant alias name
VICKY_B = SyntheticPerson(
    name="Vicky",
    aliases=("Vikram Singh",),
    name_variants=("Vikrum Singh",),
    father_name="Harbans Singh",
    age=32,
    gender="Male",
    occupation="Mechanic",
    address="House 45, Gali No 3, Laxmi Nagar, Delhi 110092",
    phone="+919876543210",  # Shared phone with Case A accused
    imei="860123045678900",
    vehicle="DL01AB1234",
    account="001234567890",
)

# Hard Negative: Different Vikram Singh (different father, age, phone)
VIKRAM_SINGH_HARD_NEG = SyntheticPerson(
    name="Vikram Singh",
    aliases=(),
    name_variants=(),
    father_name="Mohan Singh",
    age=48,
    gender="Male",
    occupation="Hardware Store Owner",
    address="Village Badarpur, Mehrauli Road, New Delhi 110044",
    phone="+919833344455",  # Different phone
    imei="860123045600037",
    vehicle="HR26EF9012",
    account="006677889900",
)

# Family-Shared Phone: Two persons sharing the same phone number
POOJA_SHARMA_B = SyntheticPerson(
    name="Pooja Sharma",
    aliases=(),
    name_variants=(),
    father_name="Dinesh Sharma",
    age=26,
    gender="Female",
    occupation="Primary School Teacher",
    address="Quarter 5B, Police Colony, Model Town, Delhi 110009",
    phone="+919844455566",  # Family-shared phone
    imei="860123045600045",
    vehicle="DL04JK1122",
    account="003322114455",
)

SUNITA_SHARMA_B = SyntheticPerson(
    name="Sunita Sharma",
    aliases=(),
    name_variants=(),
    father_name="Dinesh Sharma",  # Husband/Father identifier
    age=50,
    gender="Female",
    occupation="Homemaker",
    address="Quarter 5B, Police Colony, Model Town, Delhi 110009",
    phone="+919844455566",  # Family-shared phone
    imei="860123045600045",
    vehicle="",
    account="007788991122",
)

# ---------------------------------------------------------------------------
# Additional Fictional Personas (Realistic Pan-Indian Synthetic Identities)
# ---------------------------------------------------------------------------

ADDITIONAL_PERSONAS: tuple[SyntheticPerson, ...] = (
    SyntheticPerson(
        name="Amit Patel",
        father_name="Kishore Patel",
        age=39,
        gender="Male",
        occupation="Civil Engineer",
        address="14 Anand Nagar, Sarkhej Gandhinagar Highway, Ahmedabad 380054",
        phone="+919855566677",
        imei="860123045600052",
        vehicle="GJ01MN4567",
        account="002233445566",
    ),
    SyntheticPerson(
        name="Priya Sundaram",
        father_name="Venkatesh Sundaram",
        age=34,
        gender="Female",
        occupation="Data Analyst",
        address="Flat 4A, Kaveri Towers, Mylapore, Chennai 600004",
        phone="+919866677788",
        imei="860123045600060",
        vehicle="TN07PQ7890",
        account="004455667788",
    ),
    SyntheticPerson(
        name="Mohammad Farooq",
        father_name="Abdul Rasheed",
        age=42,
        gender="Male",
        occupation="Timber Merchant",
        address="78 Lal Bazaar, Hazratbal Road, Srinagar 190006",
        phone="+919877788899",
        imei="860123045600078",
        vehicle="JK01RS1234",
        account="008899001122",
    ),
    SyntheticPerson(
        name="Sanjay Gupta",
        father_name="Radheshyam Gupta",
        age=51,
        gender="Male",
        occupation="Chartered Accountant",
        address="C-18 Shastri Nagar, Jaipur 302016",
        phone="+919888899900",
        imei="860123045600086",
        vehicle="RJ14TU5678",
        account="001122334499",
    ),
    SyntheticPerson(
        name="Gurpreet Kaur",
        father_name="Balwant Singh",
        age=29,
        gender="Female",
        occupation="Nurse",
        address="House 89, Phase 7, SAS Nagar, Mohali 160062",
        phone="+919899900011",
        imei="860123045600094",
        vehicle="PB65VW9012",
        account="003344556611",
    ),
    SyntheticPerson(
        name="Deepak Nair",
        father_name="Madhavan Nair",
        age=37,
        gender="Male",
        occupation="Electrician",
        address="Karthika House, MG Road, Ernakulam, Kochi 682016",
        phone="+919711122233",
        imei="860123045600102",
        vehicle="KL07XY3456",
        account="005566778822",
    ),
    SyntheticPerson(
        name="Kavita Joshi",
        father_name="Prakash Joshi",
        age=31,
        gender="Female",
        occupation="Content Writer",
        address="102 Mayur Park, Kothrud, Pune 411038",
        phone="+919722233344",
        imei="860123045600110",
        vehicle="MH12ZA7890",
        account="007788990033",
    ),
    SyntheticPerson(
        name="Anand Kulkarni",
        father_name="Shridhar Kulkarni",
        age=46,
        gender="Male",
        occupation="Bank Clerk",
        address="45 Tilak Wadi, Belagavi 590006",
        phone="+919733344455",
        imei="860123045600128",
        vehicle="KA22BC1234",
        account="009900112244",
    ),
    SyntheticPerson(
        name="Manish Tiwari",
        father_name="Ramakant Tiwari",
        age=38,
        gender="Male",
        occupation="Security Guard",
        address="Sector 62, Noida, Gautam Buddha Nagar 201309",
        phone="+919744455566",
        imei="860123045600136",
        vehicle="UP14DE5678",
        account="001223344555",
    ),
    SyntheticPerson(
        name="Neha Choudhury",
        father_name="Pranab Choudhury",
        age=27,
        gender="Female",
        occupation="Software Tester",
        address="Flat 3B, Brahmaputra Enclave, Christian Basti, Guwahati 781005",
        phone="+919755566677",
        imei="860123045600144",
        vehicle="AS01FG9012",
        account="003445566766",
    ),
    SyntheticPerson(
        name="Rahul Deshmukh",
        father_name="Vasant Deshmukh",
        age=33,
        gender="Male",
        occupation="Sales Executive",
        address="Plot 56, Pratap Nagar, Nagpur 440022",
        phone="+919766677788",
        imei="860123045600151",
        vehicle="MH31HJ3456",
        account="005667788977",
    ),
    SyntheticPerson(
        name="Meena Pillai",
        father_name="Sankaran Pillai",
        age=44,
        gender="Female",
        occupation="Pharmacist",
        address="TC 24/890, Thycaud, Thiruvananthapuram 695014",
        phone="+919777788899",
        imei="860123045600169",
        vehicle="KL01KL7890",
        account="007889900188",
    ),
    SyntheticPerson(
        name="Rakesh Yadav",
        father_name="Dharmendra Yadav",
        age=36,
        gender="Male",
        occupation="Dairy Distributor",
        address="Near Old Bus Stand, Civil Lines, Gurgaon 122001",
        phone="+919788899900",
        imei="860123045600177",
        vehicle="HR26MN1234",
        account="009001122399",
    ),
    SyntheticPerson(
        name="Sneha Mukhopadhyay",
        father_name="Subhash Mukhopadhyay",
        age=30,
        gender="Female",
        occupation="Graphic Designer",
        address="23 Salt Lake Sector 2, Kolkata 700091",
        phone="+919799900011",
        imei="860123045600185",
        vehicle="WB02PQ5678",
        account="001133557700",
    ),
    SyntheticPerson(
        name="Tsering Norbu",
        father_name="Sonam Norbu",
        age=35,
        gender="Male",
        occupation="Tour Guide",
        address="Main Bazaar, Leh 194101",
        phone="+919611122233",
        imei="860123045600193",
        vehicle="22BH1234AA",
        account="002244668811",
    ),
    SyntheticPerson(
        name="Ananya Sen",
        father_name="Bimal Sen",
        age=25,
        gender="Female",
        occupation="Research Fellow",
        address="Ballygunge Circular Road, Kolkata 700019",
        phone="+919622233344",
        imei="860123045600201",
        vehicle="WB06RS9012",
        account="003355779922",
    ),
    SyntheticPerson(
        name="Kamaljeet Singh",
        father_name="Jaswant Singh",
        age=40,
        gender="Male",
        occupation="Agriculture Expert",
        address="GT Road, Khanna, Ludhiana 141401",
        phone="+919633344455",
        imei="860123045600219",
        vehicle="PB10TU3456",
        account="004466880033",
    ),
    SyntheticPerson(
        name="Sunita Rao",
        father_name="Narasimha Rao",
        age=43,
        gender="Female",
        occupation="College Lecturer",
        address="Plot 78, Jubilee Hills, Hyderabad 500033",
        phone="+919644455566",
        imei="860123045600227",
        vehicle="TS09VW7890",
        account="005577991144",
    ),
)


ALL_PERSONAS: tuple[SyntheticPerson, ...] = (
    VIKRAM_SINGH_A,
    RAJESH_SHARMA_A,
    ARJUN_VERMA_A,
    VICKY_B,
    VIKRAM_SINGH_HARD_NEG,
    POOJA_SHARMA_B,
    SUNITA_SHARMA_B,
    *ADDITIONAL_PERSONAS,
)


def list_all_persons() -> list[SyntheticPerson]:
    """Return all fictional synthetic persons defined in the system."""
    return list(ALL_PERSONAS)


def get_case_a_persons() -> list[SyntheticPerson]:
    """Return synthetic persons associated with Case A."""
    return [VIKRAM_SINGH_A, RAJESH_SHARMA_A, ARJUN_VERMA_A]


def get_case_b_persons() -> list[SyntheticPerson]:
    """Return synthetic persons associated with Case B."""
    return [VICKY_B, VIKRAM_SINGH_HARD_NEG, POOJA_SHARMA_B, SUNITA_SHARMA_B]


def get_person_by_name(name: str) -> SyntheticPerson | None:
    """Find persona by exact name, alias, or variant."""
    for p in ALL_PERSONAS:
        if p.name == name or name in p.aliases or name in p.name_variants:
            return p
    return None


__all__ = [
    "ADDITIONAL_PERSONAS",
    "ALL_PERSONAS",
    "ARJUN_VERMA_A",
    "POOJA_SHARMA_B",
    "RAJESH_SHARMA_A",
    "SUNITA_SHARMA_B",
    "SYNTHETIC_LABEL",
    "VICKY_B",
    "VIKRAM_SINGH_A",
    "VIKRAM_SINGH_HARD_NEG",
    "SyntheticPerson",
    "get_case_a_persons",
    "get_case_b_persons",
    "get_person_by_name",
    "list_all_persons",
]
