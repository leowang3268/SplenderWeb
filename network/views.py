from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
import json
from .models import User, Post, Follow, Comment


def index(request):
    return render(request, "network/index.html")


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        # Check if authentication successful
        if user is not None:
            login(request, user)
            # Redirect to index page
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "network/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "network/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "network/register.html", {
                "message": "Passwords must match."
            })

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "network/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "network/register.html")

@csrf_exempt
def create_post(request):
    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=403)

        data = json.loads(request.body)
        content = data.get("content", "")
        if content.strip() == "":
            return JsonResponse({"error": "Empty content."}, status=400)
        if len(content) > 280:  # 類似 Twitter 限制
            return JsonResponse({"error": "Content too long."}, status=400)
        post = Post(user=request.user, content=content)
        post.save()
        # Serialize the post to return in the response
        return JsonResponse({"message": "Post created successfully.", "post": post.serialize()}, status=201)
    return JsonResponse({"error": "POST request required."}, status=400)

# def all_posts(request):
#     posts = Post.objects.all().order_by("-timestamp")
#     paginator = Paginator(posts, 10)
#     page_number = request.GET.get("page")
#     page_obj = paginator.get_page(page_number)

#     return render(request, "network/all_posts.html", {
#         "page_obj": page_obj
#     })

def all_posts(request):
    return render(request, "network/all_posts.html", {
        "user_authenticated": request.user.is_authenticated
    })

def posts_api(request):
    user_param = request.GET.get("user")
    following_only = request.GET.get("following") == "true"
    # Fetch all posts, using select_related for user and prefetch_related for likes
    # This optimizes database queries by reducing the number of queries made
    # when accessing related objects.
    posts = Post.objects.select_related("user").prefetch_related("likes").order_by("-timestamp")

    if user_param:
        posts = posts.filter(user__username=user_param)
    if following_only and request.user.is_authenticated:
        # Get the IDs of users that the current user is following
        followed_users = request.user.following.values_list("followed__id", flat=True)
        # Filter posts to include only those from followed users
        posts = posts.filter(user__id__in=followed_users)

    paginator = Paginator(posts, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    data = [post.serialize(user=request.user) for post in page_obj]


    return JsonResponse({
        "posts": data,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "page_number": page_obj.number
    })

def profile(request, username):
    profile_user = get_object_or_404(User, username=username)

    return render(request, "network/profile.html", {
        "profile_user": profile_user
    })


def profile_api(request, username):
    profile_user = get_object_or_404(
        User.objects.prefetch_related("followers", "following"), 
        username=username)

    following = profile_user.following.count()
    followers = profile_user.followers.count()

    is_following = False
    if request.user.is_authenticated:
        # Check if the current user is following the profile user
        is_following = Follow.objects.filter(follower=request.user, followed=profile_user).exists()

    return JsonResponse({
        "username": profile_user.username,
        "followers": followers,
        "following": following,
        "is_following": None if request.user == profile_user else is_following
    })


@csrf_exempt
@require_POST
def follow_toggle(request, username):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=403)
    
    try:
        target_user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found."}, status=404)
    
    if request.user == target_user:
        return JsonResponse({"error": "Cannot follow yourself."}, status=400)

    follow_relation, created = Follow.objects.get_or_create(
        follower=request.user,
        followed=target_user
    )
    # If the follow relation already exists, it means the user is unfollowing
    if not created:
        follow_relation.delete()
        return JsonResponse({"message": "Unfollowed."})
    return JsonResponse({"message": "Followed."})


@csrf_exempt
@require_POST
def like_toggle(request, post_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=403)

    post = get_object_or_404(Post, id=post_id)
    user = request.user
    # Check if the user has already liked the post
    if post.likes.filter(id=user.id).exists():
        post.likes.remove(user)
        return JsonResponse({"message": "Unliked", "liked": False})
    else:
        post.likes.add(user)
        return JsonResponse({"message": "Liked", "liked": True})

def following(request):
    return render(request, "network/following.html")

@csrf_exempt
@require_http_methods(["PUT"])
def edit_post(request, post_id):
    if request.method == "PUT":
        try:
            post = Post.objects.select_related("user").get(id=post_id)
        except Post.DoesNotExist:
            return JsonResponse({"error": "Post not found."}, status=404)

        if post.user != request.user:
            return JsonResponse({"error": "You can only edit your own posts."}, status=403)

        data = json.loads(request.body)
        new_content = data.get("content", "").strip()
        if not new_content:
            return JsonResponse({"error": "Content cannot be empty."}, status=400)
        if len(new_content) > 280:  # 類似 Twitter 限制
            return JsonResponse({"error": "Content too long."}, status=400)
        post.content = new_content
        post.save()
        return JsonResponse({"message": "Post updated."})

    return JsonResponse({"error": "PUT method required."}, status=400)

@require_POST
@csrf_exempt
def create_comment(request, post_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=403)

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found."}, status=404)

    data = json.loads(request.body)
    content = data.get("content", "").strip()
    if not content:
        return JsonResponse({"error": "Content cannot be empty."}, status=400)
    if len(content) > 140:  # 類似 Twitter 限制
            return JsonResponse({"error": "Content too long."}, status=400)
    comment = Comment(post=post, user=request.user, content=content)
    comment.save()

    return JsonResponse({"message": "Comment created successfully.", "comment": comment.serialize()}, status=201)

def comments_api(request, post_id): 
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found."}, status=404)

    comments = post.comments.select_related("user").order_by("-timestamp")
    data = [comment.serialize(request.user) for comment in comments]

    return JsonResponse({
        "comments": data,
        "post_id": post_id
    })

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_comment(request, comment_id):
    try:
        comment = Comment.objects.get(pk=comment_id)
    except Comment.DoesNotExist:
        return JsonResponse({"error": "Comment not found."}, status=404)
    if comment.user != request.user:
        return JsonResponse({"error": "Unauthorized."}, status=403)
    comment.delete()
    return JsonResponse({"message": "Comment deleted"})

@csrf_exempt
@require_http_methods(["PUT"])
def edit_comment(request, comment_id):
    try:
        comment = Comment.objects.get(pk=comment_id)
    except Comment.DoesNotExist:
        return JsonResponse({"error": "Comment not found."}, status=404)
    if comment.user != request.user:
        return JsonResponse({"error": "Unauthorized."}, status=403)

    data = json.loads(request.body)
    new_content = data.get("content", "").strip()
    if not new_content:
        return JsonResponse({"error": "Empty content."}, status=400)
    if len(new_content) > 140:  # 類似 Twitter 限制
            return JsonResponse({"error": "Content too long."}, status=400)
    comment.content = new_content
    comment.save()
    return JsonResponse({"comment": {
        "id": comment.id,
        "content": comment.content
    }})

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_post(request, post_id):
    try:
        post = Post.objects.get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found."}, status=404)
    if post.user != request.user:
        return JsonResponse({"error": "Unauthorized."}, status=403)
    post.delete()
    return JsonResponse({"message": "Post deleted"})
