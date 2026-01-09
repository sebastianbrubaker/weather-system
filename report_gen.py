import sqlite3
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


# -- Globals Constants ---

WMO_CODES = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    56: 'Light freezing drizzle',
    57: 'Dense freezing drizzle',
    61: 'Light rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    66: 'Light freezing rain',
    67: 'Heavy freezing rain',
    71: 'Light snowfall',
    73: 'Moderate snowfall',
    75: 'Heavy snowfall',
    77: 'Snow grains',
    80: 'Light rain showers',
    81: 'Moderate rain showers',
    82: 'Violent rain showers',
    85: 'Light snow showers',
    86: 'Heavy snow showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with slight hail',
    99: 'Thunderstorm with heavy hail',
}


# --- Data Retrieval and Manipulation ---

def fetch_weather_data(db_path: str, start_date: str, end_date: str, collected_cutoff: str):
    """
    Fetch the latest collected weather data for each (date, area) within a date range.

    Parameters
    ----------
    db_path : str
        Path to SQLite database.
    start_date : str (YYYY-MM-DD)
        Start date of the forecast window.
    end_date : str (YYYY-MM-DD)
        End date of the forecast window.
    collected_cutoff : str (YYYY-MM-DD)
        Only rows with collection_date > cutoff are used.

    Returns
    -------
    pd.DataFrame
        Cleaned weather dataset containing the latest available row per (date, area).
    """
    # Use global DB path by default
    if db_path is None:
        db_path = DB_PATH

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print(f"Failed to connect to DB: {e}")
        return pd.DataFrame()

    # SQL Query:
    # 1. Filter to desired date range
    # 2. Filter away stale data (older than cutoff)
    # 3. Pick the most recent collection_date for each (date, area)
    query = """
    SELECT *
    FROM openmeteo AS om
    WHERE om.date BETWEEN ? AND ?
      AND om.collection_date = (
            SELECT MAX(collection_date)
            FROM openmeteo AS sub
            WHERE sub.date = om.date
              AND sub.area = om.area
              AND sub.collection_date > ?
      )
    ORDER BY area, date;
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(start_date, end_date, collected_cutoff)
    )

    conn.close()

    # Convert date strings → datetime for easier sorting & formatting
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["collection_date"] = pd.to_datetime(df["collection_date"])

    return df


def format_weather_data_for_report(df: pd.DataFrame, varif: bool = False) -> dict[str, pd.DataFrame]:
    """
    Take DB dateframe and convert it into a dictionary of formatted dataframes:

    Parameters
    ----------
    df : pd.DataFrame
        Weather dataframe
    varif : bool
        If True area and collection date column will be incleded for manual inspection purposes.
        False by default.
    
    Returns
    -------
    dict[str, pd.DataFrame]
        Weather dataframe { area_name : formatted_df }
            formatted_df columns:
                Date | high | low | precip_percent | precip_mm | precip_type

    """
    if df.empty:
        return {}

    # Add weather code description
    df['wmo_interpretation'] = df['weather_code'].map(WMO_CODES).fillna('None')

    # Format date for display
    df['date'] = pd.to_datetime(df['date'])
    df['date_formatted'] = df['date'].dt.strftime('%a %b %d')

    # Build dict { area : df }
    area_dict = {}
    for area_name, g in df.groupby('area'):
        formatted = pd.DataFrame({
            'Date': g['date_formatted'],
            'High Temp (°C)': g['high_temp'].round(1),
            'Low Temp (°C)': g['low_temp'].round(1),
            'Precip (%)': g['precipitation_percent'].round(1),
            'Snow (mm)': g['snow_mm'].round(1),
            'Precip (mm)': g['precipitation_mm'].round(1),
            # 'Conditions': g['wmo_interpretation'], 
        })

        if varif:
            formatted['Col Date'] = g['collection_date']
            formatted['Area'] = g['area']

        area_dict[area_name] = formatted.reset_index(drop=True)

    return area_dict


# --- PDF Report Generation ---

def generate_report(area_df_dict: dict[str, pd.DataFrame], report_title: str,
                    date_range: str, prepared_for_str: str, summary_str: str,
                    notes_str: str, out_f_p: str,
                    ) -> None:
    """
    Generate a multi-page PDF weather report with one page per area.

    Parameters
    ----------
    area_df_dict : dict[str, pd.DataFrame]
        Mapping of area names to formatted forecast DataFrames used to
        populate each page's table.
    report_title : str
        Title displayed at the top of the report.
    date_range : str
        Human-readable date range shown below the title.
    prepared_for_str : str
        Client name shown below title.
    summary_str : str
        Short summary string included in the "At a glance" section.
    notes_str : str
        Additional notes on the report.
    out_f_p : str
        File path for the output PDF.

    Returns
    -------
    None
    """
    doc = SimpleDocTemplate(out_f_p, pagesize=letter)

    content = []

    # Define styles
    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_heading = styles['Heading1']
    style_heading.fontSize = 16

    style_title = styles['Heading1'].clone('TitleStyle')  # Clone the existing Heading1 style
    style_title.fontSize = 20  # Set a smaller font size
    style_title.alignment = 1   # Center alignment

    style_dates = styles['Normal'].clone('DateStyle')  # Clone the existing Heading2 style
    style_dates.fontSize = 11  # Set a smaller font size
    style_dates.alignment = 1   # Center alignment

    table_style = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])

    title = Paragraph(report_title, style_title)
    date_text = Paragraph(f'<u>{date_range}</u>', style_dates)
    prepared_for = Paragraph(prepared_for_str, style_dates)

    content.extend([title, date_text, Spacer(1, 12), prepared_for, Spacer(1, 24)])

    if not summary_str is None:
        summary = Paragraph(
            f'<br/><b>At a glance:</b> {summary_str} <br/>',
            style_normal,
        )
        content.extend([summary])
    
    if not notes_str is None:        
        notes = Paragraph(
            f'<br/><b>Notes:</b> {notes_str} <br/>',
            style_normal,
        )
        content.extend([notes])

    content.extend([Spacer(1, 28)])

    
    first = True # Bool flag for page breaks 
    for area_name, df in area_df_dict.items():
        
        if not first:
            content.append(PageBreak())
        first = False

        content.append(Paragraph(text=f'{area_name}', style=style_heading))
        # content.append(Spacer(1, 1))

        # Convert the DataFrame into a list-of-lists (ReportLab table format)
        table_data = [df.columns.tolist()] + df.values.tolist()

        # Build table
        table = Table(table_data)

        # Copy base style
        t_style = TableStyle(table_style.getCommands())

        # Color code cells by temperature
        for col_idx in range(1,3): # Iterate columns
            for row_idx in range(1, len(table_data)):  # Iterate rows and skip header 
                temp = table_data[row_idx][col_idx]

                if temp <= 1:
                    color = colors.lightcoral
                elif temp <= 2.5:
                    color = colors.lightgoldenrodyellow
                elif temp <= 4:
                    color = colors.lightblue
                else:
                    color = None

                if color:
                    t_style.add(
                        'BACKGROUND',
                        (col_idx, row_idx), (col_idx, row_idx),
                        color
                    )

        table.setStyle(t_style)
        content.append(KeepTogether([table, Spacer(1, 8)]))

    doc.build(content)
    print(f'PDF report at: {out_f_p}')


def main():
    db_path = 'data/weather.db'
    start_date = '2026-01-09'
    end_date='2026-01-23'
    collected_cutoff='2026-01-08'

    report_title = 'Weather Forecast for CRD, BC, Canada'
    prepared_for_str = 'Prepared for: Avenue Road Property Maintenance'
    date_range = 'Jan 09 - Jan 23'
    summary_str = None
    notes_str = 'Conditional formatting:  temp ≤ 4: blue,  temp ≤ 2.5: yellow,  temp ≤ 1: red.'

    report_f_p = 'reports/weather_report_2026-01-09_2026-01-23.pdf'

    df = fetch_weather_data(db_path, start_date, end_date, collected_cutoff)
    area_df_dict = format_weather_data_for_report(df, varif=False)
    generate_report(area_df_dict, report_title, date_range, prepared_for_str, summary_str, notes_str, report_f_p)


if __name__ == '__main__':
    main()
