from rest_framework.exceptions import APIException


class HospitalsUnavailable(APIException):
    status_code = 503
    default_detail = "Hospital search is temporarily unavailable. Please try again shortly."
    default_code = "hospitals_unavailable"
