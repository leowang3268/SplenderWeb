
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login", views.login_view, name="login"),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    path("create", views.create_post, name="create_post"), 
    path("api/posts", views.posts_api, name="posts_api"), # API endpoint for posts 
    path("all", views.all_posts, name="all_posts"), # view for all posts
    path("profile/<str:username>", views.profile, name="profile"),
    path("api/profile/<str:username>", views.profile_api, name="profile_api"), # API endpoint for profile
    path("api/follow/<str:username>", views.follow_toggle, name="follow_toggle"), # API endpoint for follow toggle
    path("api/like/<int:post_id>", views.like_toggle, name="like"), # API endpoint for like toggle
    path("following", views.following, name="following"),
    path("api/edit/<int:post_id>", views.edit_post, name="edit_post"), # API endpoint for editing a post
    path("api/comments/<int:post_id>", views.comments_api, name="comments_api"), # API endpoint for commenting on a post
    path("api/comments/<int:post_id>/create", views.create_comment, name="create_comment"), # API endpoint for adding a comment
    path("api/comments/<int:post_id>/<int:comment_id>/delete", views.delete_comment, name="delete_comment"), # API endpoint for deleting a comment
    path("api/comments/<int:post_id>/<int:comment_id>/edit", views.edit_comment, name="edit_comment"), # API endpoint for editing a comment
]
