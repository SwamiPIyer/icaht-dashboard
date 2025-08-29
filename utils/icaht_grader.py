import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ICahtGrader:
    def __init__(self):
        self.anc_500_threshold = 501  # Use 501 to detect values ≤ 500
        self.anc_100_threshold = 101  # Use 101 to detect values ≤ 100
        self.recovery_days = 3  # Days required for neutrophil recovery
    
    def grade_early_icaht(self, df_early):
        """Grade early ICAHT (days 0-30)"""
        results = []
        
        for patient_id in df_early['patient_id'].unique():
            patient_data = df_early[df_early['patient_id'] == patient_id].copy()
            patient_data = patient_data.sort_values('time_post_inf')
            
            # Calculate exceedances for ANC ≤ 500
            exceedances_500 = self._calculate_exceedances(
                patient_data, self.anc_500_threshold, below=True
            )
            
            # Calculate exceedances for ANC ≤ 100
            exceedances_100 = self._calculate_exceedances(
                patient_data, self.anc_100_threshold, below=True
            )
            
            # Get maximum durations
            max_duration_500 = max([e['duration'] for e in exceedances_500], default=0)
            max_duration_100 = max([e['duration'] for e in exceedances_100], default=0)
            
            # Check for grade 4 special cases
            grade_4_special = self._check_grade_4_special_cases(
                patient_data, exceedances_500
            )
            
            # Assign grade
            grade = self._assign_early_grade(
                max_duration_500, max_duration_100, grade_4_special
            )
            
            results.append({
                'patient_id': patient_id,
                'duration_below_500_max': max_duration_500,
                'duration_below_100_max': max_duration_100,
                'early_icaht_grade': grade,
                'grade_4_special': grade_4_special,
                'exceedances_500': len(exceedances_500),
                'exceedances_100': len(exceedances_100)
            })
        
        return pd.DataFrame(results)
    
    def grade_late_icaht(self, df_late):
        """Grade late ICAHT (days 31+)"""
        results = []
        
        for patient_id in df_late['patient_id'].unique():
            patient_data = df_late[df_late['patient_id'] == patient_id].copy()
            
            if len(patient_data) == 0:
                # No data for late period
                results.append({
                    'patient_id': patient_id,
                    'anc_1': np.nan,
                    'anc_2': np.nan,
                    'late_icaht_grade': 'Grade 0'
                })
                continue
            
            # Get 2 lowest ANC values
            anc_values = patient_data['anc'].dropna().sort_values()
            
            anc_1 = anc_values.iloc[0] if len(anc_values) > 0 else np.nan
            anc_2 = anc_values.iloc[1] if len(anc_values) > 1 else np.nan
            
            # Assign grade
            grade = self._assign_late_grade(anc_1, anc_2)
            
            results.append({
                'patient_id': patient_id,
                'anc_1': anc_1,
                'anc_2': anc_2,
                'late_icaht_grade': grade,
                'anc_count': len(anc_values)
            })
        
        return pd.DataFrame(results)
    
    def _calculate_exceedances(self, patient_data, threshold, below=True):
        """Calculate exceedances (periods below/above threshold)"""
        if below:
            condition = patient_data['anc_final'] < threshold
        else:
            condition = patient_data['anc_final'] >= threshold
        
        # Remove NaN values
        valid_data = patient_data.dropna(subset=['anc_final'])
        if len(valid_data) == 0:
            return []
        
        condition = condition.reindex(valid_data.index, fill_value=False)
        
        exceedances = []
        in_exceedance = False
        current_exceedance = None
        
        for idx, row in valid_data.iterrows():
            if condition.loc[idx] and not in_exceedance:
                # Start new exceedance
                in_exceedance = True
                current_exceedance = {
                    'start_day': row['time_post_inf'],
                    'start_date': row['date'],
                    'end_day': row['time_post_inf'],
                    'end_date': row['date'],
                    'duration': 1
                }
            elif condition.loc[idx] and in_exceedance:
                # Continue exceedance
                current_exceedance['end_day'] = row['time_post_inf']
                current_exceedance['end_date'] = row['date']
                current_exceedance['duration'] = (
                    current_exceedance['end_day'] - current_exceedance['start_day'] + 1
                )
            elif not condition.loc[idx] and in_exceedance:
                # End exceedance
                in_exceedance = False
                exceedances.append(current_exceedance)
                current_exceedance = None
        
        # Handle exceedance that continues to end of data
        if in_exceedance and current_exceedance:
            exceedances.append(current_exceedance)
        
        # Join adjacent exceedances if recovery period is too short
        exceedances = self._join_adjacent_exceedances(exceedances, valid_data)
        
        return exceedances
    
    def _join_adjacent_exceedances(self, exceedances, patient_data):
        """Join adjacent exceedances if recovery period is insufficient"""
        if len(exceedances) <= 1:
            return exceedances
        
        joined_exceedances = []
        current_exceedance = exceedances[0].copy()
        
        for i in range(1, len(exceedances)):
            next_exceedance = exceedances[i]
            
            # Check gap between exceedances
            gap_days = next_exceedance['start_day'] - current_exceedance['end_day'] - 1
            
            if gap_days <= self.recovery_days - 1:  # -1 because we need 3 consecutive days
                # Join exceedances
                current_exceedance['end_day'] = next_exceedance['end_day']
                current_exceedance['end_date'] = next_exceedance['end_date']
                current_exceedance['duration'] = (
                    current_exceedance['end_day'] - current_exceedance['start_day'] + 1
                )
            else:
                # Keep separate
                joined_exceedances.append(current_exceedance)
                current_exceedance = next_exceedance.copy()
        
        joined_exceedances.append(current_exceedance)
        return joined_exceedances
    
    def _check_grade_4_special_cases(self, patient_data, exceedances_500):
        """Check for special grade 4 cases"""
        if not exceedances_500:
            return False
        
        # Get last day with ANC data
        last_day_data = patient_data.dropna(subset=['anc_final']).iloc[-1]
        last_day = last_day_data['time_post_inf']
        
        for exceedance in exceedances_500:
            # Check if exceedance starts in days 0-3 and continues to end of follow-up
            if (exceedance['start_day'] <= 3 and 
                exceedance['end_day'] == last_day):
                return True
        
        return False
    
    def _assign_early_grade(self, duration_500, duration_100, grade_4_special):
        """Assign early ICAHT grade based on durations"""
        if grade_4_special:
            return "Grade 4"
        
        if duration_500 == 0 and duration_100 == 0:
            return "Grade 0"
        elif duration_500 in range(1, 7) and duration_100 < 7:
            return "Grade 1"
        elif duration_500 in range(7, 14) and duration_100 < 7:
            return "Grade 2"
        elif ((duration_500 in range(14, 31) and duration_100 < 7) or
              (duration_500 < 31 and duration_100 in range(7, 14))):
            return "Grade 3"
        elif duration_500 >= 31 or duration_100 >= 14:
            return "Grade 4"
        else:
            return "Grade 0"
    
    def _assign_late_grade(self, anc_1, anc_2):
        """Assign late ICAHT grade based on nadir ANC values"""
        if pd.isna(anc_1):
            return "Grade 0"
        
        # Check conditions based on lowest ANC
        if ((anc_1 in range(1001, 1501) and (pd.isna(anc_2) or anc_2 <= 1500)) or
            (anc_1 in range(1001, 1501) and pd.isna(anc_2))):
            return "Grade 1"
        elif ((anc_1 in range(501, 1001) and (pd.isna(anc_2) or anc_2 <= 1500)) or
              (anc_1 in range(501, 1001) and pd.isna(anc_2))):
            return "Grade 2"
        elif ((anc_1 in range(101, 501) and (pd.isna(anc_2) or anc_2 <= 1500)) or
              (anc_1 in range(101, 501) and pd.isna(anc_2))):
            return "Grade 3"
        elif anc_1 <= 100:
            return "Grade 4"
        else:
            return "Grade 0"
    
    def combine_grades(self, early_grades, late_grades):
        """Combine early and late ICAHT grades"""
        # Get all patient IDs
        all_patients = set(early_grades['patient_id'].tolist() + 
                          late_grades['patient_id'].tolist())
        
        combined = []
        for patient_id in all_patients:
            early_data = early_grades[early_grades['patient_id'] == patient_id]
            late_data = late_grades[late_grades['patient_id'] == patient_id]
            
            result = {'patient_id': patient_id}
            
            # Add early grade data
            if len(early_data) > 0:
                early_row = early_data.iloc[0]
                result.update({
                    'early_icaht_grade': early_row['early_icaht_grade'],
                    'duration_below_500_max': early_row['duration_below_500_max'],
                    'duration_below_100_max': early_row['duration_below_100_max'],
                    'grade_4_special': early_row['grade_4_special']
                })
            else:
                result.update({
                    'early_icaht_grade': 'Grade 0',
                    'duration_below_500_max': 0,
                    'duration_below_100_max': 0,
                    'grade_4_special': False
                })
            
            # Add late grade data
            if len(late_data) > 0:
                late_row = late_data.iloc[0]
                result.update({
                    'late_icaht_grade': late_row['late_icaht_grade'],
                    'anc_1': late_row['anc_1'],
                    'anc_2': late_row['anc_2'],
                    'anc_count': late_row['anc_count']
                })
            else:
                result.update({
                    'late_icaht_grade': 'Grade 0',
                    'anc_1': np.nan,
                    'anc_2': np.nan,
                    'anc_count': 0
                })
            
            combined.append(result)
        
        return pd.DataFrame(combined)
    
    def generate_summary(self, final_grades, processed_data):
        """Generate summary statistics"""
        total_patients = len(final_grades)
        
        # Early ICAHT distribution
        early_dist = final_grades['early_icaht_grade'].value_counts().to_dict()
        
        # Late ICAHT distribution
        late_dist = final_grades['late_icaht_grade'].value_counts().to_dict()
        
        # Special cases
        grade_4_special_count = final_grades['grade_4_special'].sum()
        
        # Data quality metrics
        early_data_quality = self._assess_data_quality(processed_data['early'])
        late_data_quality = self._assess_data_quality(processed_data['late'])
        
        return {
            'total_patients': total_patients,
            'early_icaht_distribution': early_dist,
            'late_icaht_distribution': late_dist,
            'grade_4_special_cases': int(grade_4_special_count),
            'data_quality': {
                'early': early_data_quality,
                'late': late_data_quality
            }
        }
    
    def _assess_data_quality(self, df):
        """Assess data quality metrics"""
        if len(df) == 0:
            return {'patients_with_data': 0, 'interpolation_rate': 0}
        
        total_patients = df['patient_id'].nunique()
        
        # Calculate interpolation rate
        total_values = len(df)
        interpolated_values = df['anc_final'].isna().sum()
        interpolation_rate = interpolated_values / total_values if total_values > 0 else 0
        
        return {
            'patients_with_data': total_patients,
            'interpolation_rate': round(interpolation_rate * 100, 2)
        }
