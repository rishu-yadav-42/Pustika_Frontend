import os
from app import create_app
from models import db, User, Category, Book, Chapter, AudioFile, Favorite, ReadingHistory
from utils.tts_engine import convert_text_to_audio

def seed_database():
    app = create_app()
    with app.app_context():
        print("Resetting database for exact matching Pustika layout...")
        db.drop_all()
        db.create_all()
        
        # 1. Create Users
        admin = User(username='Shatrughan Yadav', email='rishuyadav962@gmail.com', is_admin=True)
        admin.set_password('Rishu@123')
        db.session.add(admin)
            
        test_user = User(username='johndoe', email='user@ebook.com', is_admin=False)
        test_user.set_password('user123')
        db.session.add(test_user)
        db.session.commit()

        # 2. Categories
        categories_data = [
            {"name": "Fiction", "slug": "fiction", "desc": "Classic and modern fiction masterpieces."},
            {"name": "Self-Help", "slug": "self-help", "desc": "Personal development and growth."},
            {"name": "Technology", "slug": "technology", "desc": "Programming, software craftsmanship & AI."},
            {"name": "History", "slug": "history", "desc": "World history and human civilizations."},
            {"name": "Education", "slug": "education", "desc": "Academic & foundational learning."},
            {"name": "Motivation", "slug": "motivation", "desc": "Inspiration, mindsets and success."}
        ]
        
        cat_map = {}
        for c in categories_data:
            cat = Category(name=c['name'], slug=c['slug'], description=c['desc'])
            db.session.add(cat)
            db.session.commit()
            cat_map[c['slug']] = cat

        # 3. The 15 Exact Books (Shelf 1, Shelf 2, Shelf 3)
        all_books = [
            # --- SHELF 1 (Top Shelf) ---
            {
                "id": 1,
                "title": "Atomic Habits",
                "author": "James Clear",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "atomic_habits.svg",
                "description": "An Easy & Proven Way to Build Good Habits & Break Bad Ones. Tiny changes, remarkable results.",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Surprising Power of Atomic Habits\n\nYou do not rise to the level of your goals. You fall to the level of your systems.\n\nGoals are good for setting a direction, but systems are best for making progress. In this chapter, we will explore how small, consistent changes can lead to remarkable results over time."
            },
            {
                "id": 2,
                "title": "The Alchemist",
                "author": "Paulo Coelho",
                "category_slug": "fiction",
                "language": "English",
                "cover_image": "the_alchemist.svg",
                "description": "A magical story of Santiago, an Andalusian shepherd boy who yearns to travel in search of a worldly treasure.",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Shepherd's Dream\n\nThe boy's name was Santiago. Dusk was falling as the boy arrived with his herd at an abandoned church. The roof had fallen in long ago, and an enormous sycamore had grown on the spot where the sacristy had once stood."
            },
            {
                "id": 3,
                "title": "Ikigai",
                "author": "Héctor García",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "ikigai.svg",
                "description": "The Japanese Secret to a Long and Happy Life. Discover your purpose in life.",
                "is_featured": True,
                "text": "Chapter 1\n\nIkigai: The Art of Staying Young While Growing Old\n\nWhatever you do, don't retire! Having a clear ikigai - a reason to jump out of bed in the morning - is one of the key longevity secrets of Okinawa."
            },
            {
                "id": 4,
                "title": "Deep Work",
                "author": "Cal Newport",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "deep_work.svg",
                "description": "Rules for Focused Success in a Distracted World.",
                "is_featured": True,
                "text": "Chapter 1\n\nDeep Work is Valuable\n\nDeep work is the ability to focus without distraction on a cognitively demanding task. It's a skill that allows you to quickly master complicated information."
            },
            {
                "id": 5,
                "title": "Think and Grow Rich",
                "author": "Napoleon Hill",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "think_and_grow_rich.svg",
                "description": "The landmark bestseller on wealth, success and personal achievement.",
                "is_featured": True,
                "text": "Chapter 1\n\nThoughts Are Things\n\nTruly, thoughts are things, and powerful things at that, when they are mixed with definiteness of purpose, persistence, and a burning desire for their translation into riches."
            },

            # --- SHELF 2 (Middle Shelf) ---
            {
                "id": 6,
                "title": "Sapiens",
                "author": "Yuval Noah Harari",
                "category_slug": "history",
                "language": "English",
                "cover_image": "sapiens.svg",
                "description": "A Brief History of Humankind. Explore how Homo sapiens came to dominate planet Earth.",
                "is_featured": True,
                "text": "Chapter 1\n\nAn Animal of No Significance\n\nAbout 13.5 billion years ago, matter, energy, time and space came into being in what is known as the Big Bang."
            },
            {
                "id": 7,
                "title": "The Psychology of Money",
                "author": "Morgan Housel",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "psychology_of_money.svg",
                "description": "Timeless lessons on wealth, greed, and happiness.",
                "is_featured": True,
                "text": "Chapter 1\n\nNo One's Crazy\n\nYour personal experiences with money make up maybe 0.00000001% of what happens in the world, but maybe 80% of how you think the world works."
            },
            {
                "id": 8,
                "title": "Zero to One",
                "author": "Peter Thiel",
                "category_slug": "technology",
                "language": "English",
                "cover_image": "zero_to_one.svg",
                "description": "Notes on Startups, or How to Build the Future.",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Challenge of the Future\n\nWhenever we create something new, we go from 0 to 1. The act of creation is singular, as is the moment of creation."
            },
            {
                "id": 9,
                "title": "Rich Dad Poor Dad",
                "author": "Robert Kiyosaki",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "rich_dad_poor_dad.svg",
                "description": "What the Rich Teach Their Kids About Money That the Poor and Middle Class Do Not!",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Rich Don't Work for Money\n\nThe poor and the middle class work for money. The rich have money work for them."
            },
            {
                "id": 10,
                "title": "Do Epic Shit",
                "author": "Ankur Warikoo",
                "category_slug": "motivation",
                "language": "English",
                "cover_image": "do_epic_shit.svg",
                "description": "Reflections on life, relationships, money, and habits.",
                "is_featured": True,
                "text": "Chapter 1\n\nSuccess & Failure\n\nYou do not succeed because you never failed. You succeed because you never stopped failing."
            },

            # --- SHELF 3 (Bottom Shelf) ---
            {
                "id": 11,
                "title": "Clean Code",
                "author": "Robert C. Martin",
                "category_slug": "technology",
                "language": "English",
                "cover_image": "clean_code.svg",
                "description": "A Handbook of Agile Software Craftsmanship.",
                "is_featured": True,
                "text": "Chapter 1\n\nClean Code Principles\n\nEven bad code can function. But if code isn't clean, it can bring a development organization to its knees."
            },
            {
                "id": 12,
                "title": "Data Science for Everyone",
                "author": "Robert C. Martin",
                "category_slug": "technology",
                "language": "English",
                "cover_image": "data_science.svg",
                "description": "A practical intro to data science and software engineering principles.",
                "is_featured": True,
                "text": "Chapter 1\n\nFoundations of Data Science\n\nData science is the systematic study of data to extract meaningful insights and predictions for complex domains."
            },
            {
                "id": 13,
                "title": "The 5 AM Club",
                "author": "Robin Sharma",
                "category_slug": "motivation",
                "language": "English",
                "cover_image": "the_5am_club.svg",
                "description": "Own Your Morning. Elevate Your Life.",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Dangerous Action\n\nTake control of your mornings to take control of your destiny and achieve extraordinary peak performance."
            },
            {
                "id": 14,
                "title": "The Subtle Art of Not Giving a F*ck",
                "author": "Mark Manson",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "subtle_art.svg",
                "description": "A Counterintuitive Approach to Living a Good Life.",
                "is_featured": True,
                "text": "Chapter 1\n\nDon't Try\n\nThe key to a good life is not giving a fuck about more; it's giving a fuck about less, giving a fuck about only what is true and immediate and important."
            },
            {
                "id": 15,
                "title": "Mindset",
                "author": "Carol S. Dweck",
                "category_slug": "self-help",
                "language": "English",
                "cover_image": "mindset.svg",
                "description": "The New Psychology of Success.",
                "is_featured": True,
                "text": "Chapter 1\n\nThe Mindsets\n\nFor twenty years, my research has shown that the view you adopt for yourself profoundly affects the way you lead your life."
            }
        ]

        for bdata in all_books:
            cat = cat_map.get(bdata['category_slug'])
            new_book = Book(
                id=bdata['id'],
                title=bdata['title'],
                author=bdata['author'],
                description=bdata['description'],
                category_id=cat.id if cat else 1,
                language=bdata['language'],
                cover_image=bdata['cover_image'],
                is_featured=bdata['is_featured']
            )
            db.session.add(new_book)
            db.session.commit()
            
            chap = Chapter(
                book_id=new_book.id,
                chapter_number=1,
                title=bdata['title'] + " - Chapter 1",
                text_content=bdata['text']
            )
            db.session.add(chap)
            db.session.commit()
            
            # Synthesize initial audio fallback
            try:
                result = convert_text_to_audio(
                    text=chap.text_content,
                    book_id=new_book.id,
                    chapter_number=chap.chapter_number,
                    language=new_book.language
                )
                audio = AudioFile(
                    chapter_id=chap.id,
                    file_path=result['file_path'],
                    duration_seconds=result['duration_seconds'],
                    voice_engine=result['voice_engine']
                )
                db.session.add(audio)
                db.session.commit()
            except Exception as e:
                print(f"Skipping audio generation for {new_book.title}: {e}")

        print("Database seeded with 15 exact books successfully!")

if __name__ == '__main__':
    seed_database()
