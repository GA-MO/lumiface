import 'package:dio/dio.dart';

import '../models.dart';

Dio newDio(String baseUrl) => Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      validateStatus: (_) => true,
    ));

Options bearer(String token) => Options(headers: {'Authorization': 'Bearer $token'});

String reasonCode(Response<dynamic> r) {
  final detail = r.data is Map ? (r.data as Map)['detail'] : null;
  if (detail is Map && detail['reason_code'] is String) return detail['reason_code'] as String;
  return 'HTTP_${r.statusCode}';
}

String? detailMessage(Response<dynamic> r) {
  final detail = r.data is Map ? (r.data as Map)['detail'] : null;
  return detail is String ? detail : null;
}

Never throwEnrolError(Response<dynamic> r) {
  final detail = r.data is Map ? (r.data as Map)['detail'] : null;
  if (detail is Map<String, dynamic>) {
    throw LumifaceException(reasonCode(r), detail['details'] as Map<String, dynamic>?);
  }
  throw LumifaceException(reasonCode(r), {'detail': detail});
}
