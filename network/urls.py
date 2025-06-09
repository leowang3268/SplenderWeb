
from django.urls import path

from . import views

urlpatterns = [
    # 頁面路由
    path("", views.index, name="index"),
    path("login", views.login_view, name="login"),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    path("all", views.all_posts, name="all_posts"),
    path("following", views.following, name="following"),
    path("profile/<str:username>", views.profile, name="profile"),
    
    # API 路由 - 使用更清晰的分組
    path("api/posts/", views.posts_api, name="posts_api"),
    path("api/posts/create/", views.create_post, name="create_post"),
    path("api/posts/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("api/posts/<int:post_id>/delete/", views.delete_post, name="delete_post"),
    path("api/posts/<int:post_id>/like/", views.like_toggle, name="like_toggle"),
    
    # 評論相關 API
    path("api/posts/<int:post_id>/comments/", views.comments_api, name="comments_api"),
    path("api/posts/<int:post_id>/comments/create/", views.create_comment, name="create_comment"),
    path("api/comments/<int:comment_id>/edit/", views.edit_comment, name="edit_comment"),
    path("api/comments/<int:comment_id>/delete/", views.delete_comment, name="delete_comment"),
    
    # 用戶相關 API
    path("api/users/<str:username>/", views.profile_api, name="profile_api"),
    path("api/users/<str:username>/follow/", views.follow_toggle, name="follow_toggle"),
]
