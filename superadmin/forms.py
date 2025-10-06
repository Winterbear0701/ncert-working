from django import forms
from .models import UploadedBook

class UploadBookForm(forms.ModelForm):
    class Meta:
        model = UploadedBook
        fields = ['file','original_filename','standard','subject','chapter']
