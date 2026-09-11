from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=80)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class PDFUploadForm(FlaskForm):
    pdf_file = FileField(
        "University result PDF",
        validators=[
            FileRequired(),
            FileAllowed(["pdf"], "Only PDF files are accepted."),
        ],
    )
    submit = SubmitField("Upload PDF")
