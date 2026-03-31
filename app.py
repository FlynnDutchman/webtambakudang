import streamlit as st
import ee
import geemap.foliumap as geemap
import pandas as pd
import json

# Konfigurasi Halaman Web
st.set_page_config(layout="wide", page_title="Dashboard Tambak Udang")

# ==========================================
# 1. AUTENTIKASI (TANPA POP-UP LOGIN)
# ==========================================
try:
    # Mengambil kunci rahasia dari server Streamlit
    key_dict = json.loads(st.secrets["EE_KEY"])
    credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_dict)
    ee.Initialize(credentials, project='eee-rezaauliafazrin')
except Exception as e:
    st.error("Gagal terhubung ke Earth Engine. Pastikan kredensial (EE_KEY) sudah dimasukkan di pengaturan Streamlit.")
    st.stop()

# ==========================================
# 2. PERSIAPAN DATA & FUNGSI (SENTINEL-2)
# ==========================================
poi_path = 'projects/eee-rezaauliafazrin/assets/TAMBAKUDANG'
POI = ee.FeatureCollection(poi_path)

@st.cache_data # Mencegah web menghitung ulang saat di-refresh
def process_s2_yearly(year):
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        cloud_mask = 1 << 10
        cirrus_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
        return image.updateMask(mask).divide(10000).copyProperties(image, ['system:time_start'])

    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    
    collection = (s2.filterDate(f'{year}-01-01', f'{year}-12-31')
                    .filterBounds(POI)
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                    .map(mask_s2_clouds))

    image = collection.median().clip(POI)
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')

    return image, ndvi, ndwi

img_19, ndvi_19, ndwi_19 = process_s2_yearly(2019)
img_24, ndvi_24, ndwi_24 = process_s2_yearly(2024)

# ==========================================
# 3. PERHITUNGAN LUAS AREA
# ==========================================
total_area_ha = POI.geometry().area().getInfo() / 10000

def get_water_area(ndwi_img):
    water_mask = ndwi_img.gt(0)
    area_img = water_mask.multiply(ee.Image.pixelArea())
    area_sqm = area_img.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=POI, scale=10, maxPixels=1e13
    ).getInfo().get('NDWI', 0)
    return area_sqm / 10000

water_area_19 = get_water_area(ndwi_19)
water_area_24 = get_water_area(ndwi_24)
delta_area = water_area_24 - water_area_19

def get_stats(image, name):
    return image.reduceRegion(reducer=ee.Reducer.mean(), geometry=POI, scale=10, maxPixels=1e13).getInfo()

stats_19 = {**get_stats(ndwi_19, 'NDWI')}
stats_24 = {**get_stats(ndwi_24, 'NDWI')}

# ==========================================
# 4. UI DASHBOARD (MENGGUNAKAN STREAMLIT)
# ==========================================
st.markdown("""
<div style="background: linear-gradient(135deg, #1e3a8a, #3b82f6); padding: 20px; border-radius: 12px; color: white; margin-bottom: 20px;">
    <h2 style="margin: 0;">🦐 Dashboard Pemantauan Tambak Udang</h2>
    <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 14px;">Analisis Ekstrasi Area Air & Vegetasi Berbasis Sentinel-2 (2019 vs 2024)</p>
</div>
""", unsafe_allow_html=True)

# Kartu Angka (Metrics)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Area ROI", f"{total_area_ha:.2f} Ha")
col2.metric("Luas Tambak (2019)", f"{water_area_19:.2f} Ha")
col3.metric("Luas Tambak (2024)", f"{water_area_24:.2f} Ha")
col4.metric("Perubahan Lahan Air", f"{'+' if delta_area >= 0 else ''}{delta_area:.2f} Ha")

st.write("---")
st.write("**📊 Rata-rata Nilai Indeks (NDWI) Seluruh Area:**")
df_stats = pd.DataFrame([stats_19, stats_24], index=['Tahun 2019', 'Tahun 2024']).round(4)
st.dataframe(df_stats, use_container_width=True)

# ==========================================
# 5. RENDER PETA (FOLIUMAP)
# ==========================================
st.info("💡 **Panduan Peta:** Geser garis di tengah peta ke kiri/kanan untuk membandingkan **Area Air (NDWI)** antara 2019 dan 2024.")

Map = geemap.Map(height=600)
Map.centerObject(POI, 14)

ndwi_vis = {'min': -0.3, 'max': 0.5, 'palette': ['#8c510a', '#d8b365', '#f6e8c3', '#c7eae5', '#5ab4ac', '#01665e']}

left_layer = geemap.ee_tile_layer(ndwi_19, ndwi_vis, 'NDWI 2019')
right_layer = geemap.ee_tile_layer(ndwi_24, ndwi_vis, 'NDWI 2024')
Map.split_map(left_layer, right_layer)

Map.addLayer(POI.style(color='red', fillColor='00000000', width=2), {}, 'Batas SHP Tambak', True)

# Tampilkan ke web Streamlit
Map.to_streamlit(height=600)