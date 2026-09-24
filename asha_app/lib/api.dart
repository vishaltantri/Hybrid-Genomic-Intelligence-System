import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// API client for the Genomind-India backend.
/// Token is stored in SharedPreferences; every call sends Bearer auth.
class Api {
  static const tokenKey = 'genomind_token';
  static const userKey = 'genomind_user';
  // 10.0.2.2 = host machine from the Android emulator; real devices use LAN IP.
  static String baseUrl = const String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static Future<String?> token() async =>
      (await SharedPreferences.getInstance()).getString(tokenKey);

  static Future<String?> savedUser() async =>
      (await SharedPreferences.getInstance()).getString(userKey);

  static Future<bool> login(String username, String password) async {
    final res = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/token'),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: {'username': username, 'password': password},
    );
    if (res.statusCode != 200) return false;
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(tokenKey, data['access_token'] as String);
    await prefs.setString(userKey, username);
    return true;
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(tokenKey);
    await prefs.remove(userKey);
  }

  static Future<Map<String, dynamic>> get(String path) async =>
      _send('GET', path);

  static Future<Map<String, dynamic>> post(String path, dynamic body) async =>
      _send('POST', path, body);

  static Future<Map<String, dynamic>> _send(String method, String path,
      [dynamic body]) async {
    final t = await token();
    final url = Uri.parse('$baseUrl/api/v1$path');
    final headers = {
      'Content-Type': 'application/json',
      if (t != null) 'Authorization': 'Bearer $t',
    };
    final res = method == 'GET'
        ? await http.get(url, headers: headers)
        : await http.post(url, headers: headers, body: jsonEncode(body));
    if (res.statusCode == 401) throw AuthException();
    if (res.statusCode >= 400) {
      throw Exception('API ${res.statusCode}: ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Fetch the triage questionnaire and cache it on disk for offline use.
  static Future<void> cacheQuestionnaire() async {
    final q = await get('/triage/questionnaire');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('questionnaire', jsonEncode(q));
  }

  static Future<Map<String, dynamic>?> cachedQuestionnaire() async {
    final s =
        (await SharedPreferences.getInstance()).getString('questionnaire');
    return s == null ? null : jsonDecode(s) as Map<String, dynamic>;
  }
}

class AuthException implements Exception {}
