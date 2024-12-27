from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import get_user_model, authenticate
from datetime import datetime, timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from django.utils import timezone
from ipware import get_client_ip
import http.client
import json

from .serializers import (
    UserRegistrationSerializer, OTPVerificationSerializer,
    LoginSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)
from apps.accounts.models import OTPVerification, UserSession
from apps.notifications.services.sms import OTPService

User = get_user_model()
otp_service = OTPService()

class RegistrationView(generics.GenericAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            # Check if user exists but not verified
            phone_number = serializer.validated_data['phone_number']
            existing_user = User.objects.filter(phone_number=phone_number).first()
            
            if existing_user and existing_user.is_active:
                return Response(
                    {'error': 'User with this phone number already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create or update user (inactive)
            user = existing_user or serializer.save(is_active=False)
            
            # Generate and send OTP
            otp_response = otp_service.send_otp(phone_number)
            
            if otp_response.get('pinId'):
                # Store OTP details
                OTPVerification.objects.create(
                    phone_number=phone_number,
                    otp=otp_response['pinId'],
                    expires_at=timezone.now() + timedelta(minutes=15),
                    type='registration'
                )
                
                return Response({
                    'message': 'OTP sent successfully',
                    'phone_number': str(phone_number)
                }, status=status.HTTP_200_OK)
            
            return Response({
                'error': 'Failed to send OTP'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(generics.GenericAPIView):
    serializer_class = OTPVerificationSerializer
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            otp_code = serializer.validated_data['otp']

            # Get latest OTP verification record
            otp_verification = OTPVerification.objects.filter(
                phone_number=phone_number,
                is_used=False,
                type='registration',
                expires_at__gt=timezone.now()
            ).first()

            if not otp_verification:
                return Response({
                    'error': 'Invalid or expired OTP'
                }, status=status.HTTP_400_BAD_REQUEST)

            if otp_verification.attempts >= 3:
                return Response({
                    'error': 'Maximum verification attempts exceeded'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Verify OTP with Infobip
            if self.verify_otp_with_service(otp_verification.otp, otp_code):
                user = User.objects.get(phone_number=phone_number)
                user.is_active = True
                user.save()

                otp_verification.is_used = True
                otp_verification.save()

                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'message': 'Account verified successfully',
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'user': {
                        'phone_number': str(user.phone_number),
                        'full_name': user.full_name,
                        'language': user.language
                    }
                }, status=status.HTTP_200_OK)

            otp_verification.attempts += 1
            otp_verification.save()

            return Response({
                'error': 'Invalid OTP code'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def verify_otp_with_service(self, pin_id, otp_code):
        conn = http.client.HTTPSConnection(otp_service.base_url)
        payload = json.dumps({
            "pin": otp_code,
            "pinId": pin_id
        })
        headers = {
            'Authorization': f'App {otp_service.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        conn.request("POST", "/2fa/2/pin/verify", payload, headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return data.get('verified', False)

class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            password = serializer.validated_data['password']
            device_type = serializer.validated_data.get('device_type', 'unknown')

            user = authenticate(phone_number=phone_number, password=password)
            if user:
                if not user.is_active:
                    return Response({
                        'error': 'Account is not verified'
                    }, status=status.HTTP_403_FORBIDDEN)

                refresh = RefreshToken.for_user(user)
                
                # Create session record
                ip_address, _ = get_client_ip(request)
                UserSession.objects.create(
                    user=user,
                    session_id=request.session.session_key,
                    device_type=device_type,
                    ip_address=ip_address
                )

                return Response({
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'user': {
                        'phone_number': str(user.phone_number),
                        'full_name': user.full_name,
                        'language': user.language
                    }
                })

            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Get refresh token
            refresh_token = request.data.get('refresh_token')
            token = RefreshToken(refresh_token)
            
            # Blacklist the refresh token
            token.blacklist()
            
            # Update session
            if request.session.session_key:
                UserSession.objects.filter(
                    session_id=request.session.session_key
                ).update(ended_at=timezone.now())

            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class LogoutAllView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Get all active refresh tokens for user and blacklist them
            UserSession.objects.filter(user=request.user).update(
                ended_at=timezone.now()
            )
            return Response({'message': 'Successfully logged out from all devices'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            user = User.objects.filter(phone_number=phone_number).first()
            
            if user:
                # Generate and send OTP
                otp_response = otp_service.send_otp(phone_number)
                
                if otp_response.get('pinId'):
                    OTPVerification.objects.create(
                        phone_number=phone_number,
                        otp=otp_response['pinId'],
                        expires_at=timezone.now() + timedelta(minutes=15),
                        type='password_reset'
                    )
                    
                    return Response({
                        'message': 'Password reset OTP sent'
                    })

            return Response({
                'message': 'If an account exists with this phone number, an OTP has been sent'
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            otp = serializer.validated_data['otp']
            new_password = serializer.validated_data['new_password']

            otp_verification = OTPVerification.objects.filter(
                phone_number=phone_number,
                is_used=False,
                type='password_reset',
                expires_at__gt=timezone.now()
            ).first()

            if not otp_verification:
                return Response({
                    'error': 'Invalid or expired OTP'
                }, status=status.HTTP_400_BAD_REQUEST)

            if self.verify_otp_with_service(otp_verification.otp, otp):
                user = User.objects.get(phone_number=phone_number)
                user.set_password(new_password)
                user.save()

                otp_verification.is_used = True
                otp_verification.save()

                return Response({
                    'message': 'Password reset successful'
                })

            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)