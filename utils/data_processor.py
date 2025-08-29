import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import interpolate

class DataProcessor:
    def __init__(self):
        self.required_columns = [
            'patient_id', 'cart_date', 'date', 'anc', 
            'last_fu_date', 'subsequent_therapy_date', 'progression_date'
        ]
    
    def prepare_data(self, df, settings=None):
        """Prepare data for ICAHT grading"""
        if settings is None:
            settings = {}
        
        # Validate required columns
        missing_cols = [col for col in self.required_columns if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Convert date columns
        date_columns = ['cart_date', 'date', 'last_fu_date', 'subsequent_therapy_date', 'progression_date']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Clean ANC values
        df['anc'] = pd.to_numeric(df['anc'], errors='coerce')
        
        # Prepare early ICAHT data (days 0-30)
        early_data = self._prepare_early_data(df, settings)
        
        # Prepare late ICAHT data (days 31+)
        late_data = self._prepare_late_data(df, settings)
        
        return {
            'early': early_data,
            'late': late_data,
            'original': df
        }
    
    def _prepare_early_data(self, df, settings):
        """Prepare data for early ICAHT grading (days 0-30)"""
        max_days = settings.get('early_days', 30)
        
        # Calculate days post-infusion
        df_early = df.copy()
        df_early['time_post_inf'] = (df_early['date'] - df_early['cart_date']).dt.days
        
        # Filter to early period
        df_early = df_early[
            (df_early['time_post_inf'] >= 0) & 
            (df_early['time_post_inf'] <= max_days)
        ].copy()
        
        # Handle multiple ANC values per day (keep lowest)
        df_early = df_early.groupby(['patient_id', 'time_post_inf']).agg({
            'cart_date': 'first',
            'date': 'first',
            'anc': 'min',
            'last_fu_date': 'first'
        }).reset_index()
        
        # Create complete time series for each patient
        df_early = self._create_complete_timeseries(df_early, max_days)
        
        # Interpolate missing ANC values
        df_early = self._interpolate_anc_values(df_early, settings)
        
        return df_early
    
    def _prepare_late_data(self, df, settings):
        """Prepare data for late ICAHT grading (days 31+)"""
        # Calculate days post-infusion
        df_late = df.copy()
        df_late['time_post_inf'] = (df_late['date'] - df_late['cart_date']).dt.days
        
        # Calculate end date for late period
        df_late['end_date'] = df_late[['cart_date', 'subsequent_therapy_date', 
                                      'progression_date', 'last_fu_date']].min(axis=1)
        df_late['end_date'] = df_late['end_date'].fillna(df_late['cart_date'] + timedelta(days=100))
        
        # Filter to late period
        df_late = df_late[
            (df_late['time_post_inf'] >= 31) & 
            (df_late['date'] <= df_late['end_date'])
        ].copy()
        
        # Handle multiple ANC values per day (keep lowest)
        df_late = df_late.groupby(['patient_id', 'time_post_inf']).agg({
            'cart_date': 'first',
            'date': 'first',
            'anc': 'min',
            'end_date': 'first'
        }).reset_index()
        
        return df_late
    
    def _create_complete_timeseries(self, df, max_days):
        """Create complete time series with missing days"""
        complete_data = []
        
        for patient_id in df['patient_id'].unique():
            patient_data = df[df['patient_id'] == patient_id].copy()
            
            # Get patient info
            cart_date = patient_data['cart_date'].iloc[0]
            last_fu_date = patient_data['last_fu_date'].iloc[0]
            
            # Determine follow-up period
            if pd.isna(last_fu_date):
                follow_up_days = max_days
            else:
                follow_up_days = min(max_days, (last_fu_date - cart_date).days)
            
            # Create complete date range
            for day in range(follow_up_days + 1):
                date = cart_date + timedelta(days=day)
                
                # Check if we have data for this day
                day_data = patient_data[patient_data['time_post_inf'] == day]
                
                if len(day_data) > 0:
                    # Use existing data
                    complete_data.append(day_data.iloc[0].to_dict())
                else:
                    # Create missing day entry
                    complete_data.append({
                        'patient_id': patient_id,
                        'cart_date': cart_date,
                        'date': date,
                        'time_post_inf': day,
                        'anc': np.nan,
                        'last_fu_date': last_fu_date
                    })
        
        return pd.DataFrame(complete_data)
    
    def _interpolate_anc_values(self, df, settings):
        """Interpolate missing ANC values using linear interpolation"""
        max_gap = settings.get('max_gap_days', 7)
        
        interpolated_data = []
        
        for patient_id in df['patient_id'].unique():
            patient_data = df[df['patient_id'] == patient_id].copy().sort_values('time_post_inf')
            
            # Interpolate missing values
            patient_data['anc_interpolated'] = patient_data['anc'].interpolate(
                method='linear', 
                limit=max_gap,
                limit_direction='both'
            )
            
            # Round to nearest 10 (to resemble real ANC values)
            patient_data['anc_interpolated'] = (
                patient_data['anc_interpolated'].round(-1)
            ).astype('Int64')  # Use nullable integer type
            
            # Use interpolated values where original is missing
            patient_data['anc_final'] = patient_data['anc'].fillna(patient_data['anc_interpolated'])
            
            interpolated_data.append(patient_data)
        
import numpy as np
from datetime import datetime, timedelta
from scipy import interpolate

class DataProcessor:
    def __init__(self):
        self.required_columns = [
            'patient_id', 'cart_date', 'date', 'anc', 
            'last_fu_date', 'subsequent_therapy_date', 'progression_date'
        ]
    
    def prepare_data(self, df, settings=None):
        """Prepare data for ICAHT grading"""
        if settings is None:
            settings = {}
        
        # Validate required columns
        missing_cols = [col for col in self.required_columns if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Convert date columns
        date_columns = ['cart_date', 'date', 'last_fu_date', 'subsequent_therapy_date', 'progression_date']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Clean ANC values
        df['anc'] = pd.to_numeric(df['anc'], errors='coerce')
        
        # Prepare early ICAHT data (days 0-30)
        early_data = self._prepare_early_data(df, settings)
        
        # Prepare late ICAHT data (days 31+)
        late_data = self._prepare_late_data(df, settings)
        
        return {
            'early': early_data,
            'late': late_data,
            'original': df
        }
    
    def _prepare_early_data(self, df, settings):
        """Prepare data for early ICAHT grading (days 0-30)"""
        max_days = settings.get('early_days', 30)
        
        # Calculate days post-infusion
        df_early = df.copy()
        df_early['time_post_inf'] = (df_early['date'] - df_early['cart_date']).dt.days
        
        # Filter to early period
        df_early = df_early[
            (df_early['time_post_inf'] >= 0) & 
            (df_early['time_post_inf'] <= max_days)
        ].copy()
        
        # Handle multiple ANC values per day (keep lowest)
        df_early = df_early.groupby(['patient_id', 'time_post_inf']).agg({
            'cart_date': 'first',
            'date': 'first',
            'anc': 'min',
            'last_fu_date': 'first'
        }).reset_index()
        
        # Create complete time series for each patient
        df_early = self._create_complete_timeseries(df_early, max_days)
        
        # Interpolate missing ANC values
        df_early = self._interpolate_anc_values(df_early, settings)
        
        return df_early
    
    def _prepare_late_data(self, df, settings):
        """Prepare data for late ICAHT grading (days 31+)"""
        # Calculate days post-infusion
        df_late = df.copy()
        df_late['time_post_inf'] = (df_late['date'] - df_late['cart_date']).dt.days
        
        # Calculate end date for late period
        df_late['end_date'] = df_late[['cart_date', 'subsequent_therapy_date', 
                                      'progression_date', 'last_fu_date']].min(axis=1)
        df_late['end_date'] = df_late['end_date'].fillna(df_late['cart_date'] + timedelta(days=100))
        
        # Filter to late period
        df_late = df_late[
            (df_late['time_post_inf'] >= 31) & 
            (df_late['date'] <= df_late['end_date'])
        ].copy()
        
        # Handle multiple ANC values per day (keep lowest)
        df_late = df_late.groupby(['patient_id', 'time_post_inf']).agg({
            'cart_date': 'first',
            'date': 'first',
            'anc': 'min',
            'end_date': 'first'
        }).reset_index()
        
        return df_late
    
    def _create_complete_timeseries(self, df, max_days):
        """Create complete time series with missing days"""
        complete_data = []
        
        for patient_id in df['patient_id'].unique():
            patient_data = df[df['patient_id'] == patient_id].copy()
            
            # Get patient info
            cart_date = patient_data['cart_date'].iloc[0]
            last_fu_date = patient_data['last_fu_date'].iloc[0]
            
            # Determine follow-up period
            if pd.isna(last_fu_date):
                follow_up_days = max_days
            else:
                follow_up_days = min(max_days, (last_fu_date - cart_date).days)
            
            # Create complete date range
            for day in range(follow_up_days + 1):
                date = cart_date + timedelta(days=day)
                
                # Check if we have data for this day
                day_data = patient_data[patient_data['time_post_inf'] == day]
                
                if len(day_data) > 0:
                    # Use existing data
                    complete_data.append(day_data.iloc[0].to_dict())
                else:
                    # Create missing day entry
                    complete_data.append({
                        'patient_id': patient_id,
                        'cart_date': cart_date,
                        'date': date,
                        'time_post_inf': day,
                        'anc': np.nan,
                        'last_fu_date': last_fu_date
                    })
        
        return pd.DataFrame(complete_data)
    
    def _interpolate_anc_values(self, df, settings):
        """Interpolate missing ANC values using linear interpolation"""
        max_gap = settings.get('max_gap_days', 7)
        
        interpolated_data = []
        
        for patient_id in df['patient_id'].unique():
            patient_data = df[df['patient_id'] == patient_id].copy().sort_values('time_post_inf')
            
            # Interpolate missing values
            patient_data['anc_interpolated'] = patient_data['anc'].interpolate(
                method='linear', 
                limit=max_gap,
                limit_direction='both'
            )
            
            # Round to nearest 10 (to resemble real ANC values)
            patient_data['anc_interpolated'] = (
                patient_data['anc_interpolated'].round(-1)
            ).astype('Int64')  # Use nullable integer type
            
            # Use interpolated values where original is missing
            patient_data['anc_final'] = patient_data['anc'].fillna(patient_data['anc_interpolated'])
            
            interpolated_data.append(patient_data)
        
        return pd.concat(interpolated_data, ignore_index=True)
