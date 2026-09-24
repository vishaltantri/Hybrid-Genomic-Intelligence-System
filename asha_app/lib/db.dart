import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// Offline store: every completed triage is saved locally and synced when
/// connectivity returns. The record shape matches /api/v1/triage/sync.
class Db {
  static Database? _db;

  static Future<Database> get db async {
    _db ??= await _open();
    return _db!;
  }

  static Future<Database> _open() async {
    final dir = await getDatabasesPath();
    return openDatabase(p.join(dir, 'genomind_asha.db'), version: 1,
        onCreate: (d, v) async {
      await d.execute('''
        CREATE TABLE records(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          local_id TEXT UNIQUE,
          patient_age INTEGER,
          village TEXT, district TEXT, state TEXT,
          triage_color TEXT,
          reported_symptoms TEXT,
          hpo_ids TEXT,
          transcript TEXT,
          source TEXT,
          created_at TEXT,
          sync_state TEXT DEFAULT 'pending'
        )
      ''');
    });
  }

  static Future<void> saveRecord(Map<String, dynamic> rec) async {
    final d = await db;
    await d.insert('records', {
      'local_id': rec['local_id'],
      'patient_age': rec['age'],
      'village': rec['village'] ?? '',
      'district': rec['district'] ?? '',
      'state': rec['state'] ?? '',
      'triage_color': rec['triage_color'],
      'reported_symptoms':
          (rec['reported_symptoms'] as List?)?.join('; ') ?? '',
      'hpo_ids': (rec['hpo_ids'] as List?)?.join(';') ?? '',
      'transcript': rec['transcript'] ?? '',
      'source': rec['source'] ?? 'questionnaire',
      'created_at': DateTime.now().toIso8601String(),
      'sync_state': 'pending',
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  static Future<List<Map<String, Object?>>> pending() async {
    final d = await db;
    return d.query('records', where: "sync_state = 'pending'", limit: 100);
  }

  static Future<List<Map<String, Object?>>> recent({int limit = 20}) async {
    final d = await db;
    return d.query('records', orderBy: 'id DESC', limit: limit);
  }

  static Future<void> markSynced(List<String> localIds) async {
    final d = await db;
    for (final id in localIds) {
      await d.update('records', {'sync_state': 'synced'},
          where: 'local_id = ?', whereArgs: [id]);
    }
  }

  static Future<int> pendingCount() async {
    final d = await db;
    return Sqflite.firstIntValue(
            await d.rawQuery("SELECT COUNT(*) FROM records WHERE sync_state='pending'")) ??
        0;
  }

  /// Convert a stored row to the server sync payload.
  static Map<String, dynamic> toPayload(Map<String, Object?> row) => {
        'local_id': row['local_id'],
        'age': row['patient_age'],
        'village': row['village'],
        'district': row['district'],
        'state': row['state'],
        'triage_color': row['triage_color'],
        'reported_symptoms':
            (row['reported_symptoms'] as String).split(';').where((s) => s.isNotEmpty).toList(),
        'hpo_ids': (row['hpo_ids'] as String).split(';').where((s) => s.isNotEmpty).toList(),
        'transcript': row['transcript'],
        'source': row['source'],
        'sync_state': 'synced',
      };
}
