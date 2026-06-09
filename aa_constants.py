from __future__ import annotations

from typing import Optional

import pandas as pd

DEFAULT_TICKERS = [
    'NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'AVGO', 'GOOG', 'META', 'TSLA', 'BRK-B',
    'MU', 'JPM', 'LLY', 'AMD', 'XOM', 'WMT', 'JNJ', 'INTC', 'V', 'COST',
    'CSCO', 'CAT', 'MA', 'LRCX', 'ABBV', 'NFLX', 'UNH', 'CVX', 'AMAT', 'ORCL',
    'PG', 'BAC', 'KO', 'GE', 'PLTR', 'HD', 'PM', 'GEV', 'GS', 'MRK',
    'TXN', 'KLAC', 'LIN', 'RTX', 'MS', 'WFC', 'C', 'QCOM', 'ADI', 'IBM',
    'SNDK', 'PEP', 'NEE', 'VZ', 'MCD', 'PANW', 'DIS', 'BA', 'AMGN', 'STX',
    'T', 'TMO', 'AXP', 'WDC', 'GILD', 'TJX', 'GLW', 'UNP', 'BLK', 'APH',
    'ETN', 'CRM', 'UBER', 'ANET', 'ISRG', 'WELL', 'SCHW', 'ABT', 'CRWD', 'PFE',
    'COP', 'DE', 'VRT', 'HON', 'PLD', 'APP', 'NEM', 'LOW', 'BKNG', 'CVS',
    'SPGI', 'MO', 'SBUX', 'CB', 'PWR', 'COF', 'BMY', 'PGR', 'VRTX', 'PH',
]

# Coarse sector map for the default US large-cap universe.
# Unknown tickers fall back to sector="Unknown".
SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Semiconductors", "AVGO": "Semiconductors",
    "AMD": "Semiconductors", "QCOM": "Semiconductors", "TXN": "Semiconductors", "AMAT": "Semiconductors",
    "META": "Communication", "GOOGL": "Communication", "GOOG": "Communication", "NFLX": "Communication",
    "DIS": "Communication", "VZ": "Communication",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary", "COST": "Consumer Staples", "WMT": "Consumer Staples",
    "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples", "PM": "Consumer Staples",
    "JPM": "Financials", "BAC": "Financials", "V": "Financials", "MA": "Financials", "BRK-B": "Financials",
    "LLY": "Healthcare", "UNH": "Healthcare", "JNJ": "Healthcare", "ABBV": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare", "DHR": "Healthcare", "PFE": "Healthcare",
    "XOM": "Energy", "LIN": "Materials",
    "CAT": "Industrials", "GE": "Industrials", "RTX": "Industrials",
    "CRM": "Software", "ORCL": "Software", "ADBE": "Software", "INTU": "Software", "NOW": "Software",
    "CSCO": "Technology", "IBM": "Technology", "ACN": "Technology",
}

# Additional coarse sectors for the expanded liquid-universe ticker file.
SECTOR_MAP.update({
    # Technology / Software / Semis
    "MU": "Semiconductors", "KLAC": "Semiconductors", "LRCX": "Semiconductors", "ADI": "Semiconductors",
    "MRVL": "Semiconductors", "NXPI": "Semiconductors", "ON": "Semiconductors", "MCHP": "Semiconductors",
    "PANW": "Software", "CRWD": "Software", "PLTR": "Software", "SNOW": "Software", "DDOG": "Software",
    "TEAM": "Software", "WDAY": "Software", "ZS": "Software", "NET": "Software", "MDB": "Software",
    "SHOP": "Software", "UBER": "Technology", "ABNB": "Consumer Discretionary", "DELL": "Technology", "HPQ": "Technology",
    "ANET": "Technology", "APH": "Technology", "GLW": "Technology", "HPE": "Technology", "FTNT": "Software",
    # Communication
    "TMUS": "Communication", "CMCSA": "Communication", "T": "Communication", "CHTR": "Communication", "EA": "Communication",
    "TTWO": "Communication", "RBLX": "Communication", "PINS": "Communication", "SNAP": "Communication", "SPOT": "Communication",
    # Consumer Discretionary
    "NKE": "Consumer Discretionary", "SBUX": "Consumer Discretionary", "LOW": "Consumer Discretionary", "TJX": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary", "MAR": "Consumer Discretionary", "HLT": "Consumer Discretionary", "RCL": "Consumer Discretionary",
    "CCL": "Consumer Discretionary", "GM": "Consumer Discretionary", "F": "Consumer Discretionary", "AZO": "Consumer Discretionary",
    "ORLY": "Consumer Discretionary", "CMG": "Consumer Discretionary", "YUM": "Consumer Discretionary", "DRI": "Consumer Discretionary",
    "ROST": "Consumer Discretionary", "LULU": "Consumer Discretionary", "EBAY": "Consumer Discretionary", "ETSY": "Consumer Discretionary",
    # Consumer Staples
    "MDLZ": "Consumer Staples", "MO": "Consumer Staples", "CL": "Consumer Staples", "KMB": "Consumer Staples",
    "EL": "Consumer Staples", "GIS": "Consumer Staples", "KHC": "Consumer Staples", "MNST": "Consumer Staples",
    "TGT": "Consumer Staples", "KR": "Consumer Staples", "DG": "Consumer Staples", "DLTR": "Consumer Staples",
    # Financials
    "WFC": "Financials", "GS": "Financials", "MS": "Financials", "C": "Financials", "BLK": "Financials",
    "SCHW": "Financials", "AXP": "Financials", "COF": "Financials", "USB": "Financials", "PNC": "Financials",
    "TFC": "Financials", "BK": "Financials", "AON": "Financials", "MMC": "Financials", "CB": "Financials",
    "TRV": "Financials", "PGR": "Financials", "AFL": "Financials", "MET": "Financials", "PRU": "Financials",
    "ICE": "Financials", "CME": "Financials", "SPGI": "Financials", "MCO": "Financials",
    # Healthcare
    "MRK": "Healthcare", "PFE": "Healthcare", "BMY": "Healthcare", "AMGN": "Healthcare", "GILD": "Healthcare",
    "REGN": "Healthcare", "VRTX": "Healthcare", "BIIB": "Healthcare", "ISRG": "Healthcare", "SYK": "Healthcare",
    "MDT": "Healthcare", "BSX": "Healthcare", "EW": "Healthcare", "ZBH": "Healthcare", "HCA": "Healthcare",
    "CI": "Healthcare", "HUM": "Healthcare", "CVS": "Healthcare", "ELV": "Healthcare", "MCK": "Healthcare",
    "COR": "Healthcare", "BDX": "Healthcare", "IDXX": "Healthcare", "DXCM": "Healthcare", "RMD": "Healthcare",
    "ZTS": "Healthcare", "IQV": "Healthcare", "A": "Healthcare", "WST": "Healthcare",
    # Energy
    "CVX": "Energy", "COP": "Energy", "SLB": "Energy", "EOG": "Energy", "MPC": "Energy", "PSX": "Energy",
    "VLO": "Energy", "OXY": "Energy", "KMI": "Energy", "WMB": "Energy", "HAL": "Energy", "BKR": "Energy",
    # Industrials
    "HON": "Industrials", "UNP": "Industrials", "UPS": "Industrials", "DE": "Industrials", "BA": "Industrials",
    "LMT": "Industrials", "NOC": "Industrials", "GD": "Industrials", "ETN": "Industrials", "EMR": "Industrials",
    "ITW": "Industrials", "PH": "Industrials", "CMI": "Industrials", "MMM": "Industrials", "FDX": "Industrials",
    "NSC": "Industrials", "CSX": "Industrials", "CARR": "Industrials", "OTIS": "Industrials", "PCAR": "Industrials",
    "GWW": "Industrials", "FAST": "Industrials", "JCI": "Industrials", "ROP": "Industrials", "XYL": "Industrials",
    # Materials
    "APD": "Materials", "SHW": "Materials", "ECL": "Materials", "NEM": "Materials", "FCX": "Materials",
    "DOW": "Materials", "DD": "Materials", "PPG": "Materials", "CTVA": "Materials", "MLM": "Materials", "VMC": "Materials",
    # Real Estate
    "AMT": "Real Estate", "PLD": "Real Estate", "EQIX": "Real Estate", "CCI": "Real Estate", "SPG": "Real Estate",
    "O": "Real Estate", "DLR": "Real Estate", "PSA": "Real Estate", "WELL": "Real Estate", "AVB": "Real Estate",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities", "AEP": "Utilities", "EXC": "Utilities",
    "SRE": "Utilities", "D": "Utilities", "PEG": "Utilities", "XEL": "Utilities", "ED": "Utilities",
    # SPY top-100 sector additions
    "INTC": "Semiconductors", "GEV": "Industrials", "SNDK": "Semiconductors",
    "STX": "Technology", "WDC": "Technology", "VRT": "Industrials",
    "APP": "Software", "PWR": "Industrials",
})

# Issuer aliases prevent duplicate economic exposure, e.g. GOOG and GOOGL.
ISSUER_MAP = {
    "GOOG": "ALPHABET",
    "GOOGL": "ALPHABET",
    "BRK-B": "BERKSHIRE",
}

# Correlation-cluster caps are deliberately coarser than sector caps. They limit
# theme-like concentration that can arise across official sectors, e.g. AI
# semiconductors plus data-center hardware, banks, pharma, and energy. The map is
# static and auditable; unknown tickers fall back to their coarse sector.
CORRELATION_CLUSTER_MAP = {
    # AI / semiconductors / hardware storage
    "NVDA": "AI_Semiconductor_Hardware", "AVGO": "AI_Semiconductor_Hardware", "AMD": "AI_Semiconductor_Hardware",
    "MU": "AI_Semiconductor_Hardware", "INTC": "AI_Semiconductor_Hardware", "LRCX": "AI_Semiconductor_Hardware",
    "AMAT": "AI_Semiconductor_Hardware", "KLAC": "AI_Semiconductor_Hardware", "TXN": "AI_Semiconductor_Hardware",
    "QCOM": "AI_Semiconductor_Hardware", "ADI": "AI_Semiconductor_Hardware", "MRVL": "AI_Semiconductor_Hardware",
    "SNDK": "AI_Semiconductor_Hardware", "STX": "AI_Semiconductor_Hardware", "WDC": "AI_Semiconductor_Hardware",
    # Data-center power / electrification / infrastructure
    "VRT": "AI_Power_Infrastructure", "ETN": "AI_Power_Infrastructure", "PWR": "AI_Power_Infrastructure",
    "GEV": "AI_Power_Infrastructure",
    # Mega-cap platform / communication / software growth
    "MSFT": "MegaCap_Platforms", "AAPL": "MegaCap_Platforms", "AMZN": "MegaCap_Platforms",
    "GOOGL": "MegaCap_Platforms", "GOOG": "MegaCap_Platforms", "META": "MegaCap_Platforms",
    "NFLX": "MegaCap_Platforms", "CRM": "MegaCap_Platforms", "ORCL": "MegaCap_Platforms",
    "APP": "MegaCap_Platforms", "PLTR": "MegaCap_Platforms", "PANW": "MegaCap_Platforms", "CRWD": "MegaCap_Platforms",
    # Financial clusters
    "JPM": "Banks_Brokers", "BAC": "Banks_Brokers", "GS": "Banks_Brokers", "MS": "Banks_Brokers",
    "WFC": "Banks_Brokers", "C": "Banks_Brokers", "SCHW": "Banks_Brokers", "BLK": "Banks_Brokers",
    "AXP": "Payments_Credit", "V": "Payments_Credit", "MA": "Payments_Credit", "COF": "Payments_Credit",
    "CB": "Insurance", "PGR": "Insurance",
    # Healthcare clusters
    "LLY": "Pharma_Biotech", "JNJ": "Pharma_Biotech", "ABBV": "Pharma_Biotech", "MRK": "Pharma_Biotech",
    "AMGN": "Pharma_Biotech", "GILD": "Pharma_Biotech", "PFE": "Pharma_Biotech", "BMY": "Pharma_Biotech", "VRTX": "Pharma_Biotech",
    "UNH": "Managed_Care", "CVS": "Managed_Care",
    "TMO": "Medtech_Tools", "ISRG": "Medtech_Tools", "ABT": "Medtech_Tools",
    # Cyclical / defensive clusters
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "GE": "Aerospace_Industrials", "RTX": "Aerospace_Industrials", "BA": "Aerospace_Industrials", "HON": "Aerospace_Industrials",
    "CAT": "Industrial_Cyclicals", "UNP": "Industrial_Cyclicals", "DE": "Industrial_Cyclicals", "PH": "Industrial_Cyclicals",
    "WMT": "Consumer_Defensive", "COST": "Consumer_Defensive", "PG": "Consumer_Defensive", "KO": "Consumer_Defensive",
    "PM": "Consumer_Defensive", "PEP": "Consumer_Defensive", "MO": "Consumer_Defensive",
    "HD": "Consumer_Cyclical", "LOW": "Consumer_Cyclical", "SBUX": "Consumer_Cyclical", "BKNG": "Consumer_Cyclical",
    "NKE": "Consumer_Cyclical", "TJX": "Consumer_Cyclical", "MCD": "Consumer_Cyclical", "TSLA": "Consumer_Cyclical",
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "PLD": "Real_Estate", "WELL": "Real_Estate",
    "LIN": "Materials", "NEM": "Materials",
}

VALIDATION_TOL = 1e-5


def deduplicate_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with unique column names, combining duplicate columns safely.

    Pandas concat/reindex operations require unique column indexes. Some diagnostic
    layers intentionally add scalar columns that can already exist on ranked
    snapshots. If duplicates appear, keep the first non-null value across the
    duplicate block in left-to-right order. This preserves existing per-row
    values while allowing scalar diagnostics to fill missing values.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.columns.is_unique:
        return df
    out = pd.DataFrame(index=df.index)
    seen: list[str] = []
    for col in df.columns:
        if col not in seen:
            seen.append(col)
    for col in seen:
        block = df.loc[:, df.columns == col]
        if isinstance(block, pd.Series):
            out[col] = block
        elif block.shape[1] == 1:
            out[col] = block.iloc[:, 0]
        else:
            out[col] = block.bfill(axis=1).iloc[:, 0]
    return out

def ticker_to_sector(ticker: str) -> str:
    from aa_sector_reference import lookup_sector

    return lookup_sector(ticker)

def ticker_to_issuer(ticker: str) -> str:
    tk = str(ticker).upper()
    return ISSUER_MAP.get(tk, tk)

def ticker_to_correlation_cluster(ticker: str, sector: Optional[str] = None) -> str:
    tk = str(ticker).upper()
    if tk in CORRELATION_CLUSTER_MAP:
        return CORRELATION_CLUSTER_MAP[tk]
    sec = sector if sector is not None else ticker_to_sector(tk)
    return str(sec) if str(sec) and str(sec) != "nan" else "Unknown"

FEATURE_COLUMNS = [
    "mom_252_21",
    "mom_126_21",
    "mom_63_21",
    "rev_5",
    "rev_10",
    "trend_50",
    "trend_200",
    "vol_20",
    "vol_63",
    "rel_vol_20_63",
    "idio_vol_63",
    "beta_252",
    "rel_strength_63",
    "sector_rel_strength_63",
    "sector_mom_63",
    "volume_ratio",
    "adv_20_log",
    "market_trend_200",
    "market_ret_63",
    "market_vol_20",
]


