from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
import logging
from .models import User, Post, Follow, Comment
from .serializers import PostSerializer, CommentSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)

# Constants
POST_MAX_LENGTH = 280
COMMENT_MAX_LENGTH = 140
POSTS_PER_PAGE = 10


def index(request):
    """首頁視圖"""
    return render(request, "network/index.html")


def login_view(request):
    """用戶登入視圖"""
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            logger.info(f"User {username} logged in successfully")
            return HttpResponseRedirect(reverse("index"))
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            return render(request, "network/login.html", {
                "message": "Invalid username and/or password."
            })
    return render(request, "network/login.html")


def logout_view(request):
    """用戶登出視圖"""
    if request.user.is_authenticated:
        logger.info(f"User {request.user.username} logged out")
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    """用戶註冊視圖"""
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        
        if password != confirmation:
            return render(request, "network/register.html", {
                "message": "Passwords must match."
            })

        try:
            with transaction.atomic():
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                logger.info(f"New user registered: {username}")
                return HttpResponseRedirect(reverse("index"))
        except IntegrityError:
            logger.warning(f"Registration failed - username already exists: {username}")
            return render(request, "network/register.html", {
                "message": "Username already taken."
            })
    return render(request, "network/register.html")


def _validate_content(content, max_length, content_type="Content"):
    """統一內容驗證"""
    if not content or not content.strip():
        raise ValidationError(f"{content_type} cannot be empty.")
    
    if len(content) > max_length:
        raise ValidationError(f"{content_type} too long (max {max_length} characters).")
    
    return content.strip()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_post(request):
    """創建新貼文"""
    try:
        content = _validate_content(
            request.data.get("content", ""), 
            POST_MAX_LENGTH, 
            "Post content"
        )
        
        with transaction.atomic():
            post = Post.objects.create(user=request.user, content=content)
        
        logger.info(f"User {request.user.username} created post {post.id}")
        
        # 使用原來的 serialize 方法保持相容性
        if hasattr(post, 'serialize'):
            post_data = post.serialize(user=request.user)
        else:
            post_data = {
                'id': post.id,
                'user': post.user.username,
                'content': post.content,
                'timestamp': post.timestamp.isoformat(),
                'likes_count': post.likes.count(),
                'is_liked': False
            }
        
        return Response({
            "message": "Post created successfully.", 
            "post": post_data
        }, status=status.HTTP_201_CREATED)
        
    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


def all_posts(request):
    """所有貼文頁面"""
    return render(request, "network/all_posts.html", {
        "user_authenticated": request.user.is_authenticated
    })


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def posts_api(request):
    """貼文 API - 支持分頁、篩選"""
    try:
        # 參數處理
        user_param = request.GET.get("user")
        following_only = request.GET.get("following") == "true"
        page_number = request.GET.get("page", 1)
        
        # 基礎查詢優化
        posts = Post.objects.select_related("user").prefetch_related("likes").order_by("-timestamp")

        # 篩選邏輯
        if user_param:
            posts = posts.filter(user__username=user_param)
        
        if following_only:
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required for following posts."}, 
                              status=status.HTTP_401_UNAUTHORIZED)
            
            followed_users = request.user.following.values_list("followed__id", flat=True)
            posts = posts.filter(user__id__in=followed_users)

        # 分頁處理
        paginator = Paginator(posts, POSTS_PER_PAGE)
        page_obj = paginator.get_page(page_number)
        
        # 使用原來的 serialize 方法保持相容性
        data = []
        for post in page_obj.object_list:
            if hasattr(post, 'serialize'):
                data.append(post.serialize(user=request.user))
            else:
                # 如果沒有 serialize 方法，使用基本序列化
                data.append({
                    'id': post.id,
                    'user': post.user.username,
                    'content': post.content,
                    'timestamp': post.timestamp.isoformat(),
                    'likes_count': post.likes.count(),
                    'is_liked': post.likes.filter(id=request.user.id).exists() if request.user.is_authenticated else False
                })

        # 保持原來的回應格式
        return Response({
            "posts": data,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "page_number": page_obj.number
        })
        
    except Exception as e:
        logger.error(f"Error in posts_api: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def profile(request, username):
    """用戶個人資料頁面"""
    profile_user = get_object_or_404(User, username=username)
    return render(request, "network/profile.html", {
        "profile_user": profile_user
    })


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def profile_api(request, username):
    """用戶個人資料 API"""
    try:
        profile_user = get_object_or_404(
            User.objects.prefetch_related("followers", "following"), 
            username=username
        )

        following = profile_user.following.count()
        followers = profile_user.followers.count()

        is_following = False
        if request.user.is_authenticated:
            is_following = Follow.objects.filter(
                follower=request.user, 
                followed=profile_user
            ).exists()

        return Response({
            "username": profile_user.username,
            "followers": followers,
            "following": following,
            "is_following": None if request.user == profile_user else is_following
        })
        
    except Exception as e:
        logger.error(f"Error in profile_api for user {username}: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def follow_toggle(request, username):
    """切換關注狀態"""
    try:
        target_user = get_object_or_404(User, username=username)
        
        if request.user == target_user:
            raise ValidationError("Cannot follow yourself.")

        with transaction.atomic():
            follow_relation, created = Follow.objects.get_or_create(
                follower=request.user,
                followed=target_user
            )
            
            if not created:
                follow_relation.delete()
                action = "unfollowed"
                logger.info(f"User {request.user.username} unfollowed {username}")
            else:
                action = "followed"
                logger.info(f"User {request.user.username} followed {username}")
        
        return Response({"message": f"Successfully {action}.", "action": action})
        
    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def like_toggle(request, post_id):
    """切換點讚狀態"""
    try:
        post = get_object_or_404(Post, id=post_id)
        
        with transaction.atomic():
            if post.likes.filter(id=request.user.id).exists():
                post.likes.remove(request.user)
                liked = False
                action = "unliked"
            else:
                post.likes.add(request.user)
                liked = True
                action = "liked"
        
        logger.info(f"User {request.user.username} {action} post {post_id}")
        return Response({
            "message": f"Post {action}.", 
            "liked": liked,
            "likes_count": post.likes.count()
        })
        
    except Exception as e:
        logger.error(f"Error in like_toggle for post {post_id}: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def following(request):
    """關注的用戶貼文頁面"""
    return render(request, "network/following.html")


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def edit_post(request, post_id):
    """編輯貼文"""
    try:
        post = get_object_or_404(Post.objects.select_related("user"), id=post_id)
        
        if post.user != request.user:
            raise PermissionDenied("You can only edit your own posts.")

        new_content = _validate_content(
            request.data.get("content", ""), 
            POST_MAX_LENGTH, 
            "Post content"
        )
        
        with transaction.atomic():
            post.content = new_content
            post.save()
        
        logger.info(f"User {request.user.username} edited post {post_id}")
        
        return Response({"message": "Post updated successfully."})
        
    except (ValidationError, PermissionDenied) as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_post(request, post_id):
    """刪除貼文"""
    try:
        post = get_object_or_404(Post, pk=post_id)
        
        if post.user != request.user:
            raise PermissionDenied("You can only delete your own posts.")
        
        with transaction.atomic():
            post.delete()
        
        logger.info(f"User {request.user.username} deleted post {post_id}")
        return Response({"message": "Post deleted successfully."})
        
    except PermissionDenied as e:
        return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_comment(request, post_id):
    """創建評論"""
    try:
        post = get_object_or_404(Post, id=post_id)
        
        content = _validate_content(
            request.data.get("content", ""), 
            COMMENT_MAX_LENGTH, 
            "Comment"
        )
        
        with transaction.atomic():
            comment = Comment.objects.create(post=post, user=request.user, content=content)
        
        logger.info(f"User {request.user.username} commented on post {post_id}")
        
        # 使用原來的 serialize 方法保持相容性
        if hasattr(comment, 'serialize'):
            comment_data = comment.serialize(request.user)
        else:
            comment_data = {
                'id': comment.id,
                'user': comment.user.username,
                'content': comment.content,
                'timestamp': comment.timestamp.isoformat()
            }
        
        return Response({
            "message": "Comment created successfully.", 
            "comment": comment_data
        }, status=status.HTTP_201_CREATED)
        
    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def comments_api(request, post_id): 
    """評論列表 API"""
    try:
        post = get_object_or_404(Post, id=post_id)
        comments = post.comments.select_related("user").order_by("-timestamp")
        
        # 使用原來的 serialize 方法保持相容性
        data = []
        for comment in comments:
            if hasattr(comment, 'serialize'):
                data.append(comment.serialize(request.user))
            else:
                data.append({
                    'id': comment.id,
                    'user': comment.user.username,
                    'content': comment.content,
                    'timestamp': comment.timestamp.isoformat()
                })
        
        return Response({
            "comments": data,
            "post_id": post_id
        })
        
    except Exception as e:
        logger.error(f"Error in comments_api for post {post_id}: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def edit_comment(request, comment_id):
    """編輯評論"""
    try:
        comment = get_object_or_404(Comment, pk=comment_id)
        
        if comment.user != request.user:
            raise PermissionDenied("You can only edit your own comments.")

        new_content = _validate_content(
            request.data.get("content", ""), 
            COMMENT_MAX_LENGTH, 
            "Comment"
        )
        
        with transaction.atomic():
            comment.content = new_content
            comment.save()
        
        logger.info(f"User {request.user.username} edited comment {comment_id}")
        
        return Response({
            "comment": {
                "id": comment.id,
                "content": comment.content
            }
        })
        
    except (ValidationError, PermissionDenied) as e:
        status_code = status.HTTP_403_FORBIDDEN if isinstance(e, PermissionDenied) else status.HTTP_400_BAD_REQUEST
        return Response({"error": str(e)}, status=status_code)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_comment(request, comment_id):
    """刪除評論"""
    try:
        comment = get_object_or_404(Comment, pk=comment_id)
        
        if comment.user != request.user:
            raise PermissionDenied("You can only delete your own comments.")
        
        with transaction.atomic():
            comment.delete()
        
        logger.info(f"User {request.user.username} deleted comment {comment_id}")
        return Response({"message": "Comment deleted successfully."})
        
    except PermissionDenied as e:
        return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)