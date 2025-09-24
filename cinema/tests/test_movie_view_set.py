from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient

from cinema.models import Movie, Actor, Genre
from cinema.serializers import (
    MovieListSerializer,
    MovieDetailSerializer,
    MovieImageSerializer,
    MovieSerializer,
)
from cinema.views import MovieViewSet

MOVIE_URL = reverse("cinema:movie-list")


def sample_movie(**params) -> Movie:
    defaults = {
        "title": "MovieTitle",
        "description": "MovieDescription",
        "duration": 12345,
    }
    defaults.update(params)
    return Movie.objects.create(**defaults)


class UnauthenticatedMovieViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(MOVIE_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedMovieViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="test_user@example.com",
            password="testuser",
        )
        self.client.force_authenticate(self.user)

    def test_movies_list(self):
        sample_movie()

        res = self.client.get(MOVIE_URL)
        movies = Movie.objects.all()
        serializer = MovieListSerializer(movies, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_filter_by_title_movies(self):
        movie_one = sample_movie(title="Inception")
        movie_two = sample_movie(title="Interstellar")

        res = self.client.get(MOVIE_URL, {"title": f"{movie_one.title}"})

        serializer_one = MovieListSerializer(movie_one)
        serializer_two = MovieListSerializer(movie_two)

        self.assertIn(serializer_one.data, res.data)
        self.assertNotIn(serializer_two.data, res.data)

        res = self.client.get(MOVIE_URL, {"title": "in"})
        self.assertIn(serializer_one.data, res.data)
        self.assertIn(serializer_two.data, res.data)

    def test_filter_by_actor_movies(self):
        movie_one = sample_movie(title="Inception")
        movie_two = sample_movie(title="Interstellar")

        actor_one = Actor.objects.create(first_name="Leonardo",
                                         last_name="DiCaprio"
                                         )
        actor_two = Actor.objects.create(first_name="Matthew",
                                         last_name="McConaughey"
                                         )

        movie_one.actors.add(actor_one)
        movie_two.actors.add(actor_two)

        res = self.client.get(MOVIE_URL, {"actors": f"{actor_one.id}"})

        serializer_one = MovieListSerializer(movie_one)
        serializer_two = MovieListSerializer(movie_two)

        self.assertIn(serializer_one.data, res.data)
        self.assertNotIn(serializer_two.data, res.data)

    def test_filter_by_genre_movies(self):
        movie_one = sample_movie(title="Inception")
        movie_two = sample_movie(title="Interstellar")

        genre_one = Genre.objects.create(name="action")
        genre_two = Genre.objects.create(name="science-fiction")

        movie_one.genres.add(genre_one)
        movie_two.genres.add(genre_two)

        res = self.client.get(MOVIE_URL, {"genres": f"{genre_one.id}"})

        serializer_one = MovieListSerializer(movie_one)
        serializer_two = MovieListSerializer(movie_two)

        self.assertIn(serializer_one.data, res.data)
        self.assertNotIn(serializer_two.data, res.data)

    def test_movie_detail(self):
        sample_movie()
        movie_one = sample_movie(title="Inception")

        res = self.client.get(
            reverse("cinema:movie-detail", kwargs={"pk": movie_one.id})
        )
        movie = Movie.objects.get(id=movie_one.id)
        serializer = MovieDetailSerializer(movie)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

        res = self.client.post(
            reverse("cinema:movie-detail", kwargs={"pk": movie_one.id})
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_movie_not_admin_forbidden(self):
        payload = {
            "title": "Inception",
            "description": "MovieDescription",
            "duration": 12345,
        }
        res = self.client.post(MOVIE_URL, payload)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_movie_image_not_admin_forbidden(self):
        movie = sample_movie()
        url = reverse("cinema:movie-upload-image", kwargs={"pk": movie.id})
        image = SimpleUploadedFile(
            name="test.jpg",
            content=b"fake-image-content",
            content_type="image/jpeg"
        )

        res = self.client.post(url, {"image": image}, format="multipart")
        movie.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AdminMovieViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="test_admin@example.com",
            password="testadmin",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def test_create_movie_admin(self):
        genre = Genre.objects.create(name="action")
        actor = Actor.objects.create(
            first_name="Matthew",
            last_name="McConaughey"
        )
        payload = {
            "title": "Inception",
            "description": "MovieDescription",
            "duration": 12345,
            "actors": actor.id,
            "genres": genre.id,
        }
        res = self.client.post(MOVIE_URL, payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        movie = Movie.objects.get(title="Inception")
        self.assertEqual(movie.description, "MovieDescription")
        self.assertEqual(movie.duration, 12345)

    def test_delete_movie_admin_forbidden(self):
        movie_one = sample_movie(title="Inception")
        serializer = MovieListSerializer(movie_one)

        res = self.client.get(MOVIE_URL)
        self.assertIn(serializer.data, res.data)

        res = self.client.delete(MOVIE_URL, pk=movie_one.id)
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_admin_add_movie_image(self):
        movie = sample_movie()
        url = reverse("cinema:movie-upload-image", kwargs={"pk": movie.id})

        image_io = BytesIO()
        image = Image.new("RGB", (100, 100), color="red")
        image.save(image_io, format="JPEG")
        image_io.seek(0)

        uploaded_image = SimpleUploadedFile(
            name="test.jpg", content=image_io.read(), content_type="image/jpeg"
        )

        res = self.client.post(url,
                               {"image": uploaded_image},
                               format="multipart"
                               )
        movie.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("image", res.data)
        self.assertIn("movietitle", movie.image.name)
        self.assertTrue(movie.image.name.endswith(".jpg"))


class MovieViewSetSerializerClassTest(TestCase):
    def setUp(self):
        self.viewset = MovieViewSet()

    def test_list_action_uses_list_serializer(self):
        self.viewset.action = "list"
        serializer_class = self.viewset.get_serializer_class()
        self.assertEqual(serializer_class, MovieListSerializer)

    def test_retrieve_action_uses_detail_serializer(self):
        self.viewset.action = "retrieve"
        serializer_class = self.viewset.get_serializer_class()
        self.assertEqual(serializer_class, MovieDetailSerializer)

    def test_upload_image_action_uses_image_serializer(self):
        self.viewset.action = "upload_image"
        serializer_class = self.viewset.get_serializer_class()
        self.assertEqual(serializer_class, MovieImageSerializer)

    def test_default_action_uses_base_serializer(self):
        self.viewset.action = "create"
        serializer_class = self.viewset.get_serializer_class()
        self.assertEqual(serializer_class, MovieSerializer)
