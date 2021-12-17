# -*- coding: utf-8 -*-
"""
Created in Dec 2021

@author: santi & yeying
"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
from shapely.geometry import LineString
import itertools
import base64

st.set_page_config(layout="wide")
st.sidebar.header('Drag and drop files here')
uploaded_files = st.sidebar.file_uploader('Upload routes.txt, trips.txt, stop_times.txt and shapes.txt', accept_multiple_files=True, type=['txt'])

# Get the polygons
polys = gpd.read_file("Data/UZA_Zone.geojson")
polys = polys.to_crs(epsg=4326)

 # Upload files from GTFS
if uploaded_files != []:
    for file in uploaded_files:
        name = file.name
        
        # Parse the files of the GTFS I need
        if name=='routes.txt':
            routes = pd.read_csv(file)
            if len(routes.route_short_name.unique()) == 1:
                routes['route_short_name'] = routes['route_long_name']
                
        elif name == 'trips.txt':
            trips = pd.read_csv(file)
        elif name == 'stop_times.txt':
            stop_times = pd.read_csv(file)  
        elif name == 'shapes.txt':
            aux = pd.read_csv(file)
            aux.sort_values(by=['shape_id', 'shape_pt_sequence'], ascending=True, inplace=True)
            aux = gpd.GeoDataFrame(data=aux[['shape_id']], geometry = gpd.points_from_xy(x = aux.shape_pt_lon, y=aux.shape_pt_lat))
            lines = [LineString(list(aux.loc[aux.shape_id==s, 'geometry']))  for s in aux.shape_id.unique()]
            shapes = gpd.GeoDataFrame(data=aux.shape_id.unique(), geometry = lines, columns = ['shape_id'],crs=4326)
    
    # I need the route_id in stop_times
    stop_times = pd.merge(stop_times, trips, how='left')
    
    # I need the route_short_name in trips
    trips = pd.merge(trips, routes[['route_id', 'route_short_name']])
    
    # I need the intersection and also to keep the shape_id and poly_id or index
    # Get the intersection betwee each shape and each polygon
    intersection_geo = [s.intersection(p) for s in shapes.geometry for p in polys.geometry]
    intersection = gpd.GeoDataFrame(geometry=intersection_geo)
    intersection.crs = {'init':'epsg:4326'}
    
    
    # Get the shape_ids repeated as many times as polygons there are
    shape_ids = [[s]*len(polys) for s in shapes.shape_id]
    
    # Get the polygon list as many times as shapes there are
    poly_index = [list(polys.index) for s in shapes.shape_id]
    
    # Add shape_id and polygon index to my intersection gdf
    intersection['shape_id'] = list(itertools.chain.from_iterable(shape_ids))
    # intersection['shape_id']  = intersection['shape_id']  + 'a' #this is only for keplergl to show it right
    intersection['poly_index'] = list(itertools.chain.from_iterable(poly_index))
    
    # Keep only the ones that intersected
    intersection = intersection.loc[~intersection.geometry.is_empty].reset_index()
    
    # Calculate the length of each shape
    shapes=shapes.to_crs(32411)
    shapes['length']=(gpd.GeoSeries(shapes.length))/1000*0.621371


    # Calculate the length of the intersection in km
    intersection['km_in_poly'] = intersection.geometry.to_crs(32411).length/1000
    intersection['miles_in_poly'] = intersection['km_in_poly']*0.621371

    # Get the patters with the same criteria as Remix
    # Pattern A is the one with more trips
    # If two patterns have the same number of trips, then the longer
    
    # Number of trips per shape
    trips_per_shape = trips.pivot_table('trip_id', index=['route_id', 'shape_id','direction_id'], aggfunc='count').reset_index()
    trips_per_shape.rename(columns = dict(trip_id = 'ntrips'), inplace=True)
    shapes.crs = {'init':'epsg:4326'}
    shapes['length_m'] = shapes.geometry.to_crs(epsg=4326).length
    
    # Number of stops per shape
    aux = pd.merge(stop_times[['route_id', 'stop_id', 'stop_sequence', 'trip_id']], trips[['trip_id', 'route_id', 'shape_id']], how='left')
    aux = aux.drop_duplicates(subset=['route_id', 'shape_id', 'stop_sequence']).drop('trip_id', axis=1).sort_values(by=['route_id', 'shape_id', 'stop_sequence'], ascending=True)
    stops_per_shape = aux.pivot_table('stop_sequence', index='shape_id', aggfunc='count').reset_index()
    stops_per_shape.rename(columns = dict(stop_sequence = 'nstops'), inplace=True)
    
    # Get all the variables I need to assign patterns in the same df
    patterns = pd.merge(trips_per_shape, shapes.drop('geometry', axis=1), how='left').sort_values(by=['route_id', 'ntrips', 'length'], ascending=False)
    patterns = pd.merge(patterns, stops_per_shape, how='left')
    patterns = pd.merge(routes[['route_id', 'route_short_name']], patterns, how='left')
    
    # Manage directions
    direction_0 = patterns.loc[patterns.direction_id == 0].reset_index().drop('index', axis=1)
    direction_1 = patterns.loc[patterns.direction_id == 1].reset_index().drop('index', axis=1)
    
    # Assign patterns - 
    # These are meant to match shapes in opposite directions under the same pattern 
    # But they are not the final pattern name
    assigned_patterns = pd.DataFrame()

    for r in patterns.route_short_name.unique():
        t0 = direction_0.loc[direction_0.route_short_name==r]
        t1 = direction_1.loc[direction_1.route_short_name==r]
    
        if len(t0) >= len(t1):
            longer = t0.reset_index()
            shorter = t1.reset_index()
        else:
            longer = t1.reset_index()
            shorter = t0.reset_index()
    
        abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    
        longer['aux_pattern'] = ''
        shorter['aux_pattern'] = ''
    
        for i in range(len(longer)):
            longer.loc[i, 'aux_pattern'] = abc[i]
    
            ntrips = longer.iloc[i]['ntrips']
            length_m = longer.iloc[i]['length_m']
            nstops = longer.iloc[i]['nstops']
    
            for j in range(len(shorter)):
        #         condition1 = ntrips*0.95 <= shorter.iloc[j]['ntrips'] <= ntrips*1.05
                condition2 = length_m*0.95 <= shorter.iloc[j]['length_m'] <= length_m*1.05
                condition3 = nstops*0.95 <= shorter.iloc[j]['nstops'] <= nstops*1.05
    
                if condition2 & condition3:
                    shorter.loc[j, 'aux_pattern'] = abc[i]
    
        assigned_patterns = assigned_patterns.append(longer)
        assigned_patterns = assigned_patterns.append(shorter)
        assigned_patterns.drop('index', inplace=True, axis=1)
        
    # Intersection geometries I need
    intersection1 = pd.merge(intersection, polys[['Label']], left_on='poly_index', right_on=polys.index, how='left')
    intersection1 = gpd.GeoDataFrame(data = intersection1.drop(['index','poly_index','geometry'], axis=1), geometry = intersection1.geometry)
    
    # Merge all variables
    assigned_patterns1 = pd.merge(assigned_patterns[['route_short_name', 'shape_id','aux_pattern', 'ntrips','length']], intersection1, how='right')
    assigned_patterns2 = assigned_patterns1.pivot_table(['ntrips', 'miles_in_poly'], index = ['route_short_name', 'aux_pattern'], aggfunc='sum').reset_index().sort_values(by = ['route_short_name','ntrips'], ascending=False)
    assigned_patterns2.reset_index(inplace=True)
    assigned_patterns2.drop('index', axis=1, inplace=True)
    
    # Assigned patterns depending on the total trips for both directions combined
    for r in assigned_patterns2.route_short_name.unique():
        aux = assigned_patterns2.loc[assigned_patterns2.route_short_name==r]
        pattern_list = list(abc[0:len(aux)])
        assigned_patterns2.loc[assigned_patterns2.route_short_name==r, 'pattern'] = pattern_list
    
    # Merge dataframe with the real patterns and df with the municipalities
    df1 = assigned_patterns1[['route_short_name', 'aux_pattern', 'shape_id', 'Label', 'miles_in_poly','geometry','length']]
    df1['%UZA']=df1['miles_in_poly']/df1['length']
    df2 = assigned_patterns2[['route_short_name', 'aux_pattern', 'pattern']]
    
    # This is what I need to show the table
    # I have the fields to filter by route and county
    try_this = pd.merge(df1, df2, how='left')
    table = try_this.pivot_table(values=['miles_in_poly','length','%UZA'], index=['route_short_name', 'pattern', 'Label'], aggfunc='mean').reset_index()
    table.rename(columns = dict(route_short_name = 'Route', pattern = 'Pattern', miles_in_poly = 'Miles_within',Label= 'UZA',length='Total_length'), inplace=True)
    
    # This is what I need to draw the map
    # I have the fields to filter by route and county
    gdf_intersections = gpd.GeoDataFrame(data = assigned_patterns1[['route_short_name', 'Label','length']], geometry = assigned_patterns1.geometry)
    gdf_intersections.rename(columns = dict(route_short_name = 'Route', Label = 'UZA'), inplace=True)
    
    # -------------------------------------------------------------------------------
    # --------------------------- APP -----------------------------------------------
    # -------------------------------------------------------------------------------
    # LAYING OUT THE TOP SECTION OF THE APP
    st.header("Bus Miles within UZAs")
    # LAYING OUT THE MIDDLE SECTION OF THE APP WITH THE MAPS
    col1, col2, col3= st.beta_columns((0.8, 2 ,1.2))
        
    # Select filters
    poly_names_list = list(gdf_intersections['UZA'].unique())
    lines_names_list = list(gdf_intersections['Route'].unique())
    
    poly_names_list.sort()
    lines_names_list.sort()
    
    with col1:
        st.subheader('Filters')
        #filter_polys = st.multiselect('UZAs', poly_names_list)
        filter_routes = st.multiselect('Routes', lines_names_list)
        st.subheader('Pivot dimensions')
        group_by = st.multiselect('Group by', ['Route',  'Pattern'], default = ['Route','Pattern'])
        
    #if filter_polys == []:
        #filter_polys = poly_names_list
        
    if filter_routes == []:
        filter_routes = lines_names_list
        
    # Work for the datatable
    # Aggregate data as indicated in Pivot dimensions    
    # Filter data
    table_poly = table.loc[
        (table['Route'].isin(filter_routes))
        #(table['UZA'].isin(filter_polys))
        ]
    table_poly = table_poly.pivot_table(values=['Miles_within','Total_length','%UZA'], index=group_by, aggfunc='mean').reset_index()
    table_poly['Miles_within'] = table_poly['Miles_within'].apply(lambda x: str(round(x, 2)))
    table_poly['Total_length'] = table_poly['Total_length'].apply(lambda x: str(round(x, 2)))
    table_poly['%UZA'] = table_poly['%UZA'].apply(lambda x: str(round(x, 2)))


    # Filter polygons that passed the filter
    # Merge the intersection with the number of trips per shape
    intersection_aux = pd.merge(trips, intersection1, how='right')
    intersection2 = intersection_aux.drop_duplicates(subset=['route_short_name', 'Label']).loc[:,['route_short_name', 'Label']].reset_index()
    
    # Add polygons geometries
    intersection2 = pd.merge(intersection2, polys, left_on='Label', right_on='Label', how='left')
    
    # This is what I need to select the polygons that passed the route and county filters
    route_polys = gpd.GeoDataFrame(data=intersection2[['route_short_name', 'Label']], geometry=intersection2.geometry)
    
    filtered = route_polys.loc[
        #(route_polys['Label'].isin(filter_polys))&
        (route_polys.route_short_name.isin(filter_routes))
        ]
        
    # Filter line intersections that passed the filters
    line_intersections = gdf_intersections.loc[
        (gdf_intersections['Route'].isin(filter_routes))
        #(gdf_intersections['UZA'].isin(filter_polys))
        ].__geo_interface__
    
    # Filter the shapes that passed the routes filters
    aux = trips.drop_duplicates(subset=['route_id', 'shape_id'])
    aux = pd.merge(aux, routes[['route_id', 'route_short_name']], how='left')
    shapes_filtered = pd.merge(shapes ,aux, how='left')
    shapes_filtered = gpd.GeoDataFrame(data = shapes_filtered.drop('geometry', axis=1), geometry=shapes_filtered.geometry)
    shapes_filtered = shapes_filtered.loc[shapes_filtered.route_short_name.isin(filter_routes)]
    
    # Calculate the center
    avg_lon = polys.geometry.centroid.x.mean()
    avg_lat = polys.geometry.centroid.y.mean()    

    with col2:
        st.subheader('Average Percentage within UZA = {}'.format(round(table_poly['%within'].map(float).mean(),1)))
                    # Download data
        def get_table_download_link(df):
            """Generates a link allowing the data in a given panda dataframe to be downloaded
            in:  dataframe
            out: href string
            """
            csv = df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()  # some strings <-> bytes conversions necessary here
            href = f'<a href="data:file/csv;base64,{b64}">Download csv file</a>'
            return href
        
        st.dataframe(table_poly, 900, 600)
        st.markdown(get_table_download_link(table_poly), unsafe_allow_html=True)
        
    with col3: 
        # CREATE THE MAP
        st.subheader('Map')
        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            # api_keys =  MAPBOX_API_KEY,
            initial_view_state={
                "latitude": avg_lat,
                "longitude": avg_lon,
                "zoom": 11,
                "pitch": 0,
                "height":600,
            },
            layers = [
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=filtered, 
                    # stroked = True,
                    # filled = False,
                    opacity=0.4,
                    get_fill_color= [220, 230, 245],#[150, 150, 150], #'[properties.weight * 255, properties.weight * 255, 255]',#
                    get_line_color= [255, 255, 255],
                    get_line_width = 30,
                    pickable=False,
                    extruded=False,
                    converage=1
                    ),
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=shapes_filtered, 
                    # get_fill_color=[231,51,55],
                    get_line_color=[212, 174, 174],#[50,50,50],
                    opacity=.8,
                    pickable=False,
                    extruded=True,
                    converage=1,
                    filled= True,
                    line_width_scale= 20,
                    line_width_min_pixels= 2,
                    get_line_width = 1,
                    get_radius = 100,
                    get_elevation= 30             
                    ),
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=line_intersections, 
                    # get_fill_color=[231,51,55],
                    get_line_color = [200,51,55],
                    opacity=1,
                    pickable=False,
                    extruded=False,
                    converage=1,
                    filled= True,
                    line_width_scale= 20,
                    line_width_min_pixels= 2,
                    get_line_width = 1,
                    get_radius = 100,
                    get_elevation= 30             
                    )
                ]
        ))
        
