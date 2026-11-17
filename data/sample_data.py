"""Hard-coded sample data for Riya Sharma (hostel student in India).

All monetary amounts are stored strictly as INTEGER minor units (paise for INR).
"""

CATEGORIES = [
    "Food & Mess",
    "Travel",
    "Shopping",
    "Education",
    "Bills & Recharge",
    "Entertainment",
    "Rent & Hostel",
    "Health",
    "Other",
]

RIYA_PROFILE = {
    "display_name": "Riya Sharma",
    "initials": "RS",
    "email": "riya.sharma@hostelmail.in",
    "currency": "INR",
    "locale": "en_IN",
    "theme": "system",
    "monthly_allowance_minor": 600000,   # ₹6,000.00
    "current_balance_minor": 248000,     # ₹2,480.00
    "upcoming_essentials_minor": 85000,  # ₹850.00 (mess balance + recharge due)
    "tight_threshold_minor": 10000,      # ₹100.00 / day
    "days_until_income": 12,
    "next_income_date": "2026-11-29",
    "is_sample": True,
}

# Realistic hostel student transactions in paise (minor units)
RIYA_EXPENSES = [
    {
        "id": 1,
        "date": "2026-11-17",
        "merchant": "Hostel Mess & Canteen",
        "note": "Monthly mess coupon top-up",
        "category": "Food & Mess",
        "amount_minor": 145000,
        "essential": True,
        "method": "UPI",
    },
    {
        "id": 2,
        "date": "2026-11-16",
        "merchant": "Zomato — Campus Biryani",
        "note": "Late night group study dinner",
        "category": "Food & Mess",
        "amount_minor": 24500,
        "essential": False,
        "method": "UPI",
    },
    {
        "id": 3,
        "date": "2026-11-15",
        "merchant": "Delhi Metro Card",
        "note": "Weekly student pass recharge",
        "category": "Travel",
        "amount_minor": 20000,
        "essential": True,
        "method": "UPI",
    },
    {
        "id": 4,
        "date": "2026-11-14",
        "merchant": "Campus Xerox & Print",
        "note": "DBMS notes + lab spiral binding",
        "category": "Education",
        "amount_minor": 14000,
        "essential": False,
        "method": "Cash",
    },
    {
        "id": 5,
        "date": "2026-11-13",
        "merchant": "Swiggy Instamart",
        "note": "Maggi, coffee sachets, biscuits",
        "category": "Food & Mess",
        "amount_minor": 18500,
        "essential": False,
        "method": "UPI",
    },
    {
        "id": 6,
        "date": "2026-11-11",
        "merchant": "Jio Student Pack",
        "note": "28-day 2GB/day recharge",
        "category": "Bills & Recharge",
        "amount_minor": 29900,
        "essential": True,
        "method": "UPI",
    },
    {
        "id": 7,
        "date": "2026-11-10",
        "merchant": "Spotify Student",
        "note": "Monthly music subscription",
        "category": "Entertainment",
        "amount_minor": 5900,
        "essential": False,
        "method": "UPI AutoPay",
    },
    {
        "id": 8,
        "date": "2026-11-08",
        "merchant": "Weekend Outing — Hauz Khas",
        "note": "Cold coffee & metro split with friends",
        "category": "Entertainment",
        "amount_minor": 38000,
        "essential": False,
        "method": "UPI",
    },
    {
        "id": 9,
        "date": "2026-11-06",
        "merchant": "Chai Tapri Outside Gate",
        "note": "Evening chai + bun maska",
        "category": "Food & Mess",
        "amount_minor": 4000,
        "essential": False,
        "method": "UPI",
    },
    {
        "id": 10,
        "date": "2026-11-05",
        "merchant": "Hostel Laundry & Utility",
        "note": "Shared hostel washing & iron",
        "category": "Rent & Hostel",
        "amount_minor": 32000,
        "essential": True,
        "method": "UPI",
    },
    {
        "id": 11,
        "date": "2026-11-03",
        "merchant": "Campus Medical Store",
        "note": "Vitamin D & band-aids",
        "category": "Health",
        "amount_minor": 12000,
        "essential": True,
        "method": "UPI",
    },
    {
        "id": 12,
        "date": "2026-11-02",
        "merchant": "Decathlon Socks & Bottle",
        "note": "Morning run gear",
        "category": "Shopping",
        "amount_minor": 29900,
        "essential": False,
        "method": "UPI",
    },
]

RIYA_BUDGETS = [
    {"category": "Food & Mess", "limit_minor": 220000, "spent_minor": 191500},
    {"category": "Rent & Hostel", "limit_minor": 60000, "spent_minor": 32000},
    {"category": "Travel", "limit_minor": 45000, "spent_minor": 20000},
    {"category": "Bills & Recharge", "limit_minor": 35000, "spent_minor": 29900},
    {"category": "Entertainment", "limit_minor": 50000, "spent_minor": 43900},
    {"category": "Education", "limit_minor": 40000, "spent_minor": 14000},
    {"category": "Shopping", "limit_minor": 40000, "spent_minor": 29900},
    {"category": "Health", "limit_minor": 25000, "spent_minor": 12000},
    {"category": "Other", "limit_minor": 20000, "spent_minor": 0},
]

RIYA_GOALS = [
    {
        "id": 1,
        "title": "Noise-Cancelling Headphones",
        "saved_minor": 145000,
        "target_minor": 249900,
        "deadline": "2027-01-15",
        "note": "For quiet library & hostel exam prep",
    },
    {
        "id": 2,
        "title": "Semester Break Train Home",
        "saved_minor": 90000,
        "target_minor": 140000,
        "deadline": "2026-12-20",
        "note": "3AC ticket + snacks for the ride",
    },
    {
        "id": 3,
        "title": "Rainy-Day Hostel Buffer",
        "saved_minor": 65000,
        "target_minor": 150000,
        "deadline": "2027-03-01",
        "note": "Emergency cushion before next allowance",
    },
]
