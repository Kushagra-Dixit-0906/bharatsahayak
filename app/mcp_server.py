import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("BharatSahayak Farming MCP Server")

@mcp.tool()
def get_weather_advisory(location: str, crop: str) -> str:
    """Gets the weather forecast and specific agricultural recommendations for a given location and crop.
    
    Args:
        location: The state or region in India (e.g., Punjab, Karnataka).
        crop: The crop being grown (e.g., wheat, rice, cotton).
    """
    loc = location.lower()
    crp = crop.lower()
    
    if "punjab" in loc:
        if "wheat" in crp:
            return (
                "Weather Forecast for Punjab: Light winds, sunny, temperatures around 32°C. No rain expected this week.\n"
                "Advisory: Ideal time for urea application. Soil moisture is moderate; irrigate lightly if soil is dry. "
                "Monitor for rust disease signs."
            )
        else:
            return (
                "Weather Forecast for Punjab: Sunny, temperatures around 34°C. No rain expected.\n"
                "Advisory: Ensure adequate irrigation for seasonal crops. Mulch around crops to prevent excessive soil moisture evaporation."
            )
    elif "karnataka" in loc:
        if "rice" in crp:
            return (
                "Weather Forecast for Karnataka: High humidity, scattered rainfall (15-20mm) expected in 48 hours.\n"
                "Advisory: Postpone any planned pesticide spray or fertilizer application until after the rain. "
                "Ensure proper drainage in nursery beds to avoid waterlogging."
            )
        else:
            return (
                "Weather Forecast for Karnataka: Scattered rainfall expected.\n"
                "Advisory: Clear drainage channels to prevent water accumulation."
            )
    else:
        return (
            f"Weather Forecast for {location}: Normal seasonal conditions.\n"
            f"Advisory for {crop}: Monitor local forecasts. Maintain regular weeding and watering schedules based on soil dampness."
        )

@mcp.tool()
def get_crop_disease_info(crop: str, symptoms: str) -> str:
    """Diagnoses potential crop diseases based on visible symptoms and provides treatments.
    
    Args:
        crop: The name of the crop (e.g., wheat, rice, cotton).
        symptoms: Description of the symptoms (e.g., yellow spots, white powder, wilting leaves).
    """
    crp = crop.lower()
    sym = symptoms.lower()
    
    if "rice" in crp:
        if "spot" in sym or "brown" in sym:
            return (
                "Potential Diagnosis: Brown Spot Disease (Fungal)\n"
                "Explanation: Small, circular to oval spots on leaves, usually with a yellow halo.\n"
                "Treatments:\n"
                "- Spray Mancozeb (2.5 g/L) or Carbendazim (1 g/L) if infection is severe.\n"
                "- Apply balanced potassium fertilizer.\n"
                "Preventive Measures: Use certified disease-free seeds; practice crop rotation; clear weed hosts from bunds."
            )
        elif "blast" in sym or "neck" in sym or "spindle" in sym:
            return (
                "Potential Diagnosis: Rice Blast (Fungal)\n"
                "Explanation: Spindle-shaped spots on leaves with grey centers and brown borders.\n"
                "Treatments:\n"
                "- Spray Tricyclazole 75 WP at 0.6 g/L.\n"
                "- Avoid excess nitrogen application.\n"
                "Preventive Measures: Plant resistant varieties; destroy crop residues after harvest."
            )
    elif "wheat" in crp:
        if "rust" in sym or "orange" in sym or "yellow" in sym:
            return (
                "Potential Diagnosis: Wheat Rust (Yellow/Striped or Leaf Rust)\n"
                "Explanation: Bright yellow/orange pustules forming stripes on leaves.\n"
                "Treatments:\n"
                "- Spray Propiconazole 25 EC (1 ml/L) immediately upon noticing symptoms.\n"
                "Preventive Measures: Grow rust-resistant varieties; avoid late sowing."
            )
    
    return (
        f"Potential Diagnosis: General Fungal or Nutrient deficiency for {crop}.\n"
        f"Symptoms analyzed: {symptoms}.\n"
        f"Recommended Action: Take a clear photo of the infected leaf. Apply organic Neem cake to improve soil health, "
        f"and spray 1% Neem Oil solution as a broad-spectrum organic defense. Consult local extension center if wilting persists."
    )

@mcp.tool()
def search_government_schemes(state: str, crop: str) -> str:
    """Finds available Indian government schemes, subsidies, and eligibility criteria for a given state and crop.
    
    Args:
        state: The state (e.g., Punjab, Karnataka, Haryana).
        crop: The crop (e.g., wheat, rice).
    """
    st = state.lower()
    crp = crop.lower()
    
    schemes = [
        "1. PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)\n"
        "   - Details: Direct income support of Rs. 6,000/year to all landholding farmer families.\n"
        "   - Eligibility: Small and marginal farmers with cultivable land in any state.\n"
        "   - Documents: Aadhaar, Land ownership papers, Bank account details.",
        
        "2. PMFBY (Pradhan Mantri Fasal Bima Yojana)\n"
        "   - Details: Crop insurance scheme protecting against crop failure due to natural disasters.\n"
        "   - Premium: 1.5% for Rabi crops, 2.0% for Kharif crops.\n"
        "   - Documents: Land sowing certificate, Aadhaar, Bank passbook."
    ]
    
    if "punjab" in st:
        schemes.append(
            "3. Punjab Free Power Scheme\n"
            "   - Details: Free electricity supplied to agricultural tube wells for crop irrigation.\n"
            "   - Eligibility: Registered farmers in Punjab with tube well connections."
        )
    elif "karnataka" in st:
        schemes.append(
            "3. Krishi Bhagya Scheme (Karnataka)\n"
            "   - Details: Subsidy for rainwater harvesting ponds, polythene lining, and diesel pumpsets (up to 80-90% subsidy).\n"
            "   - Eligibility: All farmers in dry-zone districts of Karnataka."
        )
        
    return "\n\n".join(schemes)

@mcp.tool()
def calculate_farming_profitability(crop: str, acreage: float, expected_yield_per_acre: float) -> str:
    """Calculates estimated costs, expected revenue, and net profit for cultivating a crop on a specific farm size.
    
    Args:
        crop: The crop name (e.g., wheat, rice, cotton).
        acreage: The farm size in acres (e.g., 2.0, 5.0).
        expected_yield_per_acre: Estimated yield in quintals (100 kg) per acre.
    """
    crp = crop.lower()
    
    if "wheat" in crp:
        cost_per_acre = 15000
        msp_per_quintal = 2275
    elif "rice" in crp or "paddy" in crp:
        cost_per_acre = 18000
        msp_per_quintal = 2183
    elif "cotton" in crp:
        cost_per_acre = 22000
        msp_per_quintal = 6620
    else:
        cost_per_acre = 16000
        msp_per_quintal = 2500
        
    total_cost = cost_per_acre * acreage
    total_yield = expected_yield_per_acre * acreage
    total_revenue = total_yield * msp_per_quintal
    net_profit = total_revenue - total_cost
    
    return (
        f"Farming Profitability Analysis for {acreage} acres of {crop}:\n"
        f"- Estimated Cost of Cultivation: Rs. {total_cost:,.2f} (Rs. {cost_per_acre:,} per acre)\n"
        f"- Expected Total Yield: {total_yield:.2f} quintals ({expected_yield_per_acre:.2f} quintals/acre)\n"
        f"- Minimum Expected Revenue (at Govt MSP of Rs. {msp_per_quintal}/quintal): Rs. {total_revenue:,.2f}\n"
        f"- Estimated Net Profit: Rs. {net_profit:,.2f}\n\n"
        f"Tips to improve profitability:\n"
        f"1. Use micro-irrigation (drip/sprinkler) to reduce water costs and increase yield.\n"
        f"2. Apply organic manure alongside chemical fertilizers (IPNM) to lower inputs cost by 15%.\n"
        f"3. Sell through e-NAM (electronic National Agriculture Market) for better price discovery."
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
