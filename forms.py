# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, IntegerField, FloatField, TextAreaField, BooleanField, FileField, RadioField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, NumberRange, Length, Regexp, EqualTo
from flask_wtf.file import FileAllowed

class LoginForm(FlaskForm):
    phone = StringField('Телефон', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

class RegisterForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    phone = StringField('Телефон', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=4)])
    submit = SubmitField('Зарегистрироваться')

class ForgotPasswordForm(FlaskForm):
    phone = StringField('Телефон', validators=[DataRequired()])
    submit = SubmitField('Далее')

class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('Новый пароль', validators=[DataRequired(), Length(min=4)])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('new_password', message='Пароли должны совпадать')])
    submit = SubmitField('Сохранить пароль')

class ReservationFilterForm(FlaskForm):
    date = StringField('Дата', validators=[DataRequired()],
                       render_kw={"type": "date"})
    start_hour = SelectField('Час начала', choices=[(f'{h:02d}', f'{h:02d}') for h in range(12, 24)])
    start_min = SelectField('Минуты начала', choices=[('00', '00'), ('30', '30')])
    end_hour = SelectField('Час окончания', choices=[(f'{h:02d}', f'{h:02d}') for h in range(12, 24)])
    end_min = SelectField('Минуты окончания', choices=[('00', '00'), ('30', '30')])
    guests = IntegerField('Гостей', validators=[DataRequired(), NumberRange(min=1, max=20)])
    submit = SubmitField('Показать схему')

class ReviewForm(FlaskForm):
    rating = SelectField('Оценка', choices=[(str(i), str(i)) for i in range(5, 0, -1)], default='5')
    text = TextAreaField('Отзыв', validators=[DataRequired()])
    submit = SubmitField('Отправить')

class CheckoutForm(FlaskForm):
    order_type = RadioField('Способ получения', choices=[('takeaway', 'Самовывоз'), ('delivery', 'Доставка')], default='takeaway')
    address_id = SelectField('Адрес доставки', coerce=int, validators=[Optional()])
    payment_method = RadioField('Способ оплаты', choices=[('card', 'Банковская карта'), ('sbp', 'СБП')], default='card')
    bonus_used = IntegerField('Использовать бонусов', validators=[NumberRange(min=0)], default=0)
    submit = SubmitField('Оплатить')

class EditProfileForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email()])
    password = PasswordField('Текущий пароль')
    new_password = PasswordField('Новый пароль', validators=[Optional(), Length(min=4)])
    submit = SubmitField('Сохранить')

class AddressForm(FlaskForm):
    address = StringField('Адрес', validators=[DataRequired()])
    submit = SubmitField('Добавить')

class PaymentForm(FlaskForm):
    card_number = StringField('Последние 4 цифры', validators=[DataRequired(), Length(min=4, max=4), Regexp(r'^\d{4}$')])
    submit = SubmitField('Добавить')

class AllergenForm(FlaskForm):
    allergen = StringField('Аллерген', validators=[DataRequired()])
    submit = SubmitField('Добавить')

# Админские формы
class AdminAddUserForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    phone = StringField('Телефон', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=4)])
    role = SelectField('Роль', choices=[('user', 'Пользователь'), ('manager', 'Менеджер'), ('hostess', 'Хостес'), ('admin', 'Админ')])
    submit = SubmitField('Создать')

class AdminEditUserForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email()])
    role = SelectField('Роль', choices=[('user', 'Пользователь'), ('manager', 'Менеджер'), ('hostess', 'Хостес'), ('admin', 'Админ')])
    new_password = PasswordField('Новый пароль (если нужно)')
    submit = SubmitField('Сохранить')

class AdminAddMenuItemForm(FlaskForm):
    name = StringField('Название', validators=[DataRequired()])
    price = FloatField('Цена', validators=[DataRequired(), NumberRange(min=0)])
    category_id = SelectField('Категория', coerce=int, validators=[DataRequired()])
    description = TextAreaField('Описание')
    available = BooleanField('Доступно', default=True)
    image_file = FileField('Фото (файл)', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'])])
    image_url = StringField('или URL изображения')
    submit = SubmitField('Добавить')

class AdminEditMenuItemForm(FlaskForm):
    name = StringField('Название', validators=[DataRequired()])
    price = FloatField('Цена', validators=[DataRequired(), NumberRange(min=0)])
    category_id = SelectField('Категория', coerce=int, validators=[DataRequired()])
    description = TextAreaField('Описание')
    available = BooleanField('Доступно')
    image_file = FileField('Фото (файл)', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'])])
    image_url = StringField('или URL изображения')
    submit = SubmitField('Сохранить')

class AdminAddTableForm(FlaskForm):
    capacity = IntegerField('Вместимость', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Расположение')
    submit = SubmitField('Добавить')

class AdminEditTableForm(FlaskForm):
    capacity = IntegerField('Вместимость', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Расположение')
    active = BooleanField('Активен')
    submit = SubmitField('Сохранить')

class AdminAddReservationForm(FlaskForm):
    user_id = SelectField('Пользователь', coerce=int, validators=[DataRequired()])
    table_id = SelectField('Стол', coerce=int, validators=[DataRequired()])
    date = StringField('Дата', validators=[DataRequired()],
                       render_kw={"type": "date"})
    start_time = StringField('Время начала', validators=[DataRequired()])
    end_time = StringField('Время окончания', validators=[DataRequired()])
    guests = IntegerField('Гостей', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Добавить')

class AdminImportForm(FlaskForm):
    datafile = FileField('JSON-файл', validators=[FileAllowed(['json'], 'Только JSON-файлы')])
    import_menu = BooleanField('Меню и категории', default=True)
    import_users = BooleanField('Пользователи', default=True)
    import_tables = BooleanField('Столы', default=True)
    submit = SubmitField('Импортировать')

class AdminChangeStatusForm(FlaskForm):
    status = SelectField('Статус', choices=[
        ('created', 'Создан'), ('paid', 'Оплачен'), ('in_progress', 'В работе'),
        ('completed', 'Завершён'), ('cancelled', 'Отменён')
    ])
    submit = SubmitField('Сменить статус')

class AdminEditOrderItemsForm(FlaskForm):
    action = HiddenField()
    menu_item_id = SelectField('Блюдо', coerce=int, validators=[Optional()])
    quantity = IntegerField('Количество', validators=[Optional(), NumberRange(min=1)], default=1)
    remove_item_id = HiddenField()
    update_item_id = HiddenField()
    new_quantity = IntegerField('Новое количество', validators=[Optional(), NumberRange(min=1)])
    submit = SubmitField('Выполнить')

class EditReservationForm(FlaskForm):
    date = StringField('Дата', validators=[DataRequired()], render_kw={"type": "date"})
    start_time = StringField('Время начала', validators=[DataRequired()])
    end_time = StringField('Время окончания', validators=[DataRequired()])
    guests = IntegerField('Гостей', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Сохранить изменения')