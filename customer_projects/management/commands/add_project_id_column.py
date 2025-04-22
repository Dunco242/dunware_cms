from django.core.management.base import BaseCommand
from django.db import connection
from customer_projects.models import Project, ProjectTeamMember

class Command(BaseCommand):
    help = 'Add project_id column to customer_projects_projectteammember table and populate it'

    def handle(self, *args, **options):
        self.stdout.write("Adding project_id column to customer_projects_projectteammember...")

        # Check if project_id column exists
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(customer_projects_projectteammember);")
            columns = [col[1] for col in cursor.fetchall()]
            if 'project_id' in columns:
                self.stdout.write(self.style.WARNING("project_id column already exists."))
                return

        # Add project_id column
        with connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE customer_projects_projectteammember
                ADD COLUMN project_id INTEGER;
            """)
            self.stdout.write(self.style.SUCCESS("Added project_id column."))

        # Populate project_id for existing rows (if any)
        project_team_members = ProjectTeamMember.objects.all()
        if project_team_members.exists():
            self.stdout.write("Populating project_id for existing ProjectTeamMember records...")
            default_project = Project.objects.first()
            if not default_project:
                self.stdout.write(self.style.WARNING("No projects found. Setting project_id to NULL."))
            else:
                for ptm in project_team_members:
                    # Assign a default project or existing project_id if available
                    ptm.project = default_project
                    ptm.save()
                self.stdout.write(self.style.SUCCESS(f"Populated project_id for {project_team_members.count()} records."))
        else:
            self.stdout.write("No existing ProjectTeamMember records to populate.")

        # Verify ForeignKey integrity
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT project_id
                FROM customer_projects_projectteammember
                WHERE project_id IS NOT NULL
                AND project_id NOT IN (SELECT id FROM customer_projects_project);
            """)
            invalid_ids = cursor.fetchall()
            if invalid_ids:
                self.stdout.write(self.style.ERROR("Found invalid project_id values. Please fix manually."))
                self.stdout.write(str(invalid_ids))
            else:
                self.stdout.write(self.style.SUCCESS("project_id values are valid."))

        self.stdout.write(self.style.SUCCESS("Operation completed. Run 'makemigrations' to update Django."))
